//! Окно net67 получает снимки и отправляет команды; сетевые задачи остаются
//! в проверенном движке 2.22.0, чтобы сохранить его встроенные маршруты.

use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use crate::ops::{Cap, Cmd, Event, State, Status};

const PAYLOAD_SHA: &str = "cb0a5c7c77a3e24dbb4e7f696c40d2b757355d51c772ea861d7471d028307f3a";
pub const CAPS: &[(&str, Cap)] = &[
    ("client_patch", Cap::ClientPatch), ("watchdog", Cap::Watchdog),
    ("dns", Cap::Dns), ("local_proxy", Cap::LocalProxy),
    ("own_proxy", Cap::OwnProxy), ("builtin_exits", Cap::BuiltinExits),
    ("group_proxy", Cap::GroupProxy), ("dns_rotation", Cap::DnsRotation),
    ("verify_tls", Cap::VerifyTls),
];

pub fn service_source() -> Result<PathBuf, String> {
    let path = std::env::current_exe().map_err(|e| e.to_string())?
        .with_file_name("ag_network.exe");
    let bytes = std::fs::read(&path).map_err(|_| "Сетевой движок Antigravity отсутствует".to_string())?;
    if hex::encode(Sha256::digest(&bytes)) != PAYLOAD_SHA {
        return Err("Сетевой движок Antigravity повреждён: переустановите net67".into());
    }
    Ok(path)
}

fn output(value: Value) {
    let mut out = io::stdout().lock();
    let _ = writeln!(out, "{value}");
    let _ = out.flush();
}

fn state_json(state: &State) -> Value {
    let kind = match state {
        State::On => "on", State::Off => "off", State::Partial(_) => "partial",
        State::OffNote(_) => "off", State::Blocked(_) => "blocked",
    };
    json!({"kind": kind, "on": state.is_on(), "note": state.note().unwrap_or("")})
}

fn status_json(s: &Status) -> Value {
    let caps: serde_json::Map<String, Value> = CAPS.iter()
        .map(|(name, cap)| (name.to_string(), state_json(s.get(*cap)))).collect();
    let mut caps = caps;
    caps.insert("bypass".into(), json!({"kind":"available","on":s.bypass_on(),"note":""}));
    json!({
        "admin": s.admin, "caps": caps,
        "pc_code": crate::hwid::pc_code(),
        "installs": s.installs.iter().map(|i| json!({
            "label": i.label, "path": i.path, "patched": i.patched, "manual": i.manual
        })).collect::<Vec<_>>(),
        "providers": s.providers.iter().map(|p| json!({"name": p.name, "enabled": p.enabled})).collect::<Vec<_>>(),
        "own_proxy": s.own_proxy_text,
        "vpn": s.vpn.map(|v| format!("{v:?}")),
        "relay_running": s.relay_running, "relay_outdated": s.relay_outdated, "rules": s.rules,
    })
}

struct Screen {
    status: Option<Status>,
    gate: crate::gate::View,
    gate_at: Instant,
}

fn headline(screen: &Screen) {
    if let Some(s) = &screen.status {
        let facts = crate::gui::status::Facts::read(s, &screen.gate, screen.gate_at.elapsed());
        let h = crate::gui::status::headline(&facts);
        output(json!({"event": "headline", "title": h.title, "detail": h.detail,
            "tone": format!("{:?}", h.tone),
            "action": h.action.map(|a| format!("{a:?}")),
            "action_label": h.action.map(|a| a.label()),
            "verify_url": screen.gate.verify.as_ref().map(|v| &v.url),
            "relay": screen.gate.relay,
        }));
    }
}

pub fn command(v: &Value) -> Result<Cmd, String> {
    let text = |name| v.get(name).and_then(Value::as_str).ok_or_else(|| format!("Нет поля {name}"));
    match text("command")? {
        "refresh" => Ok(Cmd::DeepRefresh),
        "enable_all" => Ok(Cmd::EnableAll),
        "repair" => Ok(Cmd::Repair),
        "set" => {
            let name = text("cap")?;
            let on = v.get("on").and_then(Value::as_bool).ok_or("Нет состояния переключателя")?;
            if name == "bypass" { return Ok(Cmd::SetBypass(on)); }
            let cap = CAPS.iter().find(|(n, _)| *n == name).ok_or("Неизвестный переключатель")?.1;
            Ok(Cmd::Set(cap, on))
        }
        "add_path" => {
            let path = crate::ops::resolve_manual_path(&PathBuf::from(text("path")?))
                .ok_or("В этой папке не найден Antigravity")?;
            Ok(Cmd::AddPath(path))
        }
        "forget_path" => Ok(Cmd::ForgetPath(PathBuf::from(text("path")?))),
        "own_proxy" => Ok(Cmd::SetOwnProxy(text("value")?.to_string())),
        "group_proxy" => Ok(Cmd::SetGroupKey(text("value")?.to_string())),
        "provider" => Ok(Cmd::SetProvider(text("name")?.to_string(),
            v.get("on").and_then(Value::as_bool).ok_or("Нет состояния DNS")?)),
        "provider_order" => {
            let order = v.get("order").and_then(Value::as_array).ok_or("Нет порядка DNS")?;
            let names = order.iter().map(|x| x.as_str().map(str::to_string).ok_or("Неверное имя DNS"))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(Cmd::ReorderProviders(names))
        }
        "stop" => Ok(Cmd::Stop),
        _ => Err("Неизвестная команда Antigravity".into()),
    }
}

pub fn run() {
    // Проверка файла сама по себе не запускает прокси и не меняет Windows.
    if std::env::args().any(|a| a == "--check") {
        match service_source() {
            Ok(_) => output(json!({"event":"checked","version":"2.22.0","ok":true})),
            Err(e) => { output(json!({"event":"checked","ok":false,"error":e})); std::process::exit(1); }
        }
        return;
    }
    if let Err(e) = service_source() {
        output(json!({"event":"error","message":e}));
        return;
    }
    let (tx, rx) = mpsc::channel();
    let worker = Arc::new(crate::ops::spawn(tx, Box::new(|| {})));
    let screen = Arc::new(Mutex::new(Screen {status: None, gate: Default::default(), gate_at: Instant::now()}));
    let screen_out = screen.clone();
    let printer = std::thread::spawn(move || {
        for e in rx {
            match e {
                Event::Completed(id) => output(json!({"event":"completed", "request_id":id})),
                Event::Log(level, message) => output(json!({"event":"log", "level":format!("{level:?}"), "message":message})),
                Event::Busy(message) => output(json!({"event":"busy","message":message})),
                Event::Status(s) => {
                    output(json!({"event":"status","status":status_json(&s)}));
                    let mut state = screen_out.lock().unwrap();
                    state.status = Some(*s);
                    headline(&state);
                }
            }
        }
    });
    let (gate_tx, gate_rx) = mpsc::channel();
    crate::gate::spawn_watch(gate_tx, Box::new(|| {}));
    let gate_screen = screen.clone();
    let gate_worker = worker.clone();
    std::thread::spawn(move || {
        for e in gate_rx {
            match e {
                crate::gate::Signal::Gate(view) => {
                    let mut state = gate_screen.lock().unwrap();
                    state.gate = view;
                    state.gate_at = Instant::now();
                    headline(&state);
                }
                crate::gate::Signal::MeasureVpn => gate_worker.send(Cmd::RemeasureVpn),
            }
        }
    });
    // Стареющие отметки о последнем ответе обновляются без сетевого запроса.
    let tick_screen = screen.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(5));
        headline(&tick_screen.lock().unwrap());
    });
    for line in io::stdin().lock().lines() {
        let Ok(line) = line else { break; };
        let value: Value = match serde_json::from_str(&line) {
            Ok(v) => v, Err(_) => { output(json!({"event":"error","message":"Неверная команда"})); continue; }
        };
        if value.get("command").and_then(Value::as_str) == Some("report") {
            let state = screen.lock().unwrap();
            output(json!({"event":"report", "text":crate::gui::report::build(state.status.as_ref(), &state.gate)}));
            continue;
        }
        match command(&value) {
            Ok(cmd) => {
                let stop = matches!(cmd, Cmd::Stop);
                if let Some(id) = value.get("request_id").and_then(Value::as_u64) {
                    worker.send(Cmd::Request { id, command: Box::new(cmd) });
                } else {
                    worker.send(cmd);
                }
                if stop { break; }
            }
            Err(e) => output(json!({"event":"error","message":e})),
        }
    }
    // Stop стоит в той же очереди, что патч и откат: не обрываем запись файлов.
    worker.send(Cmd::Stop);
    let _ = printer.join();
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_invalid_switch_and_missing_boolean() {
        assert!(command(&json!({"command":"set","cap":"unknown","on":true})).is_err());
        assert!(command(&json!({"command":"set","cap":"dns"})).is_err());
        assert!(matches!(command(&json!({"command":"set","cap":"dns","on":false})), Ok(Cmd::Set(Cap::Dns, false))));
    }
    #[test]
    fn off_note_does_not_turn_switch_on() {
        assert_eq!(state_json(&State::OffNote("пояснение".into()))["on"], false);
        assert_eq!(state_json(&State::Partial("частично".into()))["on"], true);
    }
}
