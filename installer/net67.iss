; Установщик net67 (Inno Setup 6).
;
; Собирается из папки artifact\, которую делает scripts\build_local.ps1.
; Готовый .exe кладётся в installer\output\.
;
; Установщик НЕ подписан: внутри корпоративной сети менеджеры ставят его
; сами, и SmartScreen покажет предупреждение «Windows защитила ваш
; компьютер» -> «Подробнее» -> «Выполнить в любом случае». Антивирус может
; забрать в карантин winws.exe и драйвер WinDivert - их нужно внести в
; исключения силами IT, иначе кнопка «Включить» будет молча не работать.
;
; Сборка:
;   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1

#define AppName        "net67"
#define AppPublisher   "net67"
#define AppExeName     "net67.exe"
#define AppId          "{{9E5A2C41-7B3D-4F18-9A66-2D8C4E7F1B05}"

; Версию подставляет build_installer.ps1 из src\config\build_info.py.
#ifndef AppVersion
  #define AppVersion "1.0.0.0"
#endif

; Корень артефакта. Переопределяется ключом /DSourceDir=...
#ifndef SourceDir
  #define SourceDir "..\artifact"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

; WinDivert - драйвер режима ядра, ставить и запускать его может только
; администратор. Без этого «Включить» не сработает, поэтому просим права
; сразу, а не в середине работы.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0

OutputDir=output
OutputBaseFilename=net67-setup-{#AppVersion}
SetupIconFile={#SourceDir}\ico\net67.ico
UninstallDisplayIcon={app}\_internal\{#AppExeName}
UninstallDisplayName={#AppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "launchatlogon"; Description: "Запускать net67 при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
; Артефакт копируется целиком, одной строкой.
;
; Перечисление папок по одной уже подвело: windivert.filter — это папка с
; наборами фильтров, а не файл, и компилятор встал на «Source file ... does
; not exist». Любая новая папка в артефакте так же молча не доехала бы до
; установленной программы.
;
; Пользовательские папки исключены явно. Полагаться на то, что в
; артефакте они пустые, нельзя: приложение запускают прямо оттуда —
; из artifact\_internal\net67.exe — и оно пишет туда свои настройки.
; Один такой запуск, и установщик разослал бы двадцати менеджерам чужой
; settings.json поверх их собственного.
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
  Excludes: "logs\*,tmp\*,settings\*,lists\user\*,presets\winws1\*,presets\winws2\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Лежит рядом с приложением: деинсталлятор зовёт его до удаления файлов.
Source: "clear_hosts.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion

[Dirs]
; Папки, куда приложение пишет само. Создаём пустыми, чтобы первый запуск
; не спотыкался о права на создание каталога в Program Files.
Name: "{app}\presets\winws1"; Permissions: users-modify
Name: "{app}\presets\winws2"; Permissions: users-modify
Name: "{app}\lists\user";     Permissions: users-modify
Name: "{app}\settings";       Permissions: users-modify
Name: "{app}\logs";           Permissions: users-modify
Name: "{app}\tmp";            Permissions: users-modify

[InstallDelete]
; Мусор прошлой версии. Пользовательские папки в списке отсутствуют
; намеренно: пресеты, списки и настройки переживают обновление.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\tmp"
Type: files;          Name: "{app}\logs\*.log"

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\_internal\{#AppExeName}"; WorkingDir: "{app}\_internal"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\_internal\{#AppExeName}"; WorkingDir: "{app}\_internal"; Tasks: desktopicon

[Run]
; Приложение стартует ТОЛЬКО из _internal: путь проверяет
; resolve_application_root() в config\runtime_layout.py.
;
; shellexec обязателен. net67.exe собран с манифестом
; requireAdministrator, а галочка «Запустить» на последней странице
; выполняется в контексте обычного пользователя. Обычный CreateProcess
; такой файл запустить не может и возвращает «недостаточно прав» —
; именно это и видел человек сразу после установки. ShellExecute умеет
; поднять UAC-запрос и запустить программу как надо.
Filename: "{app}\_internal\{#AppExeName}"; Description: "Запустить {#AppName}"; \
  WorkingDir: "{app}\_internal"; Flags: nowait postinstall skipifsilent shellexec

; Автозапуск ставим задачей планировщика, а не ключом реестра Run:
; приложению нужны права администратора, а задача с RunLevel=Highest
; поднимает его без запроса UAC на каждом входе в систему.
Filename: "schtasks.exe"; \
  Parameters: "/Create /F /TN ""net67 Autostart"" /TR ""\""{app}\_internal\{#AppExeName}\"""" /SC ONLOGON /RL HIGHEST"; \
  Flags: runhidden waituntilterminated; Tasks: launchatlogon

[UninstallRun]
; Порядок важен: сначала останавливаем то, что держит файлы, потом
; удаляем. Драйвер в ядре не даст стереть свой .sys, пока запущен.
;
; Задача планировщика.
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""net67 Autostart"""; Flags: runhidden; RunOnceId: "DelAutostartTask"

; Служба Telegram-прокси, см. TG_SERVICE_NAME в src\telegram_proxy\service.py.
Filename: "sc.exe"; Parameters: "stop net67TelegramProxy";   Flags: runhidden; RunOnceId: "StopTgProxy"
Filename: "sc.exe"; Parameters: "delete net67TelegramProxy"; Flags: runhidden; RunOnceId: "DelTgProxy"

; Процессы движка. taskkill не ругается фатально, если процесса нет.
Filename: "taskkill.exe"; Parameters: "/F /IM net67.exe /IM winws.exe /IM winws2.exe /IM amneziawg.exe"; Flags: runhidden; RunOnceId: "KillEngine"

; Драйвер WinDivert. Имена совпадают с _WINDIVERT_DRIVER_SERVICE_NAMES
; в приложении: движок переименовывает драйвер, чтобы обойти блокировки
; по имени службы, поэтому вариантов несколько.
Filename: "sc.exe"; Parameters: "stop Monkey";        Flags: runhidden; RunOnceId: "StopMonkey"
Filename: "sc.exe"; Parameters: "delete Monkey";      Flags: runhidden; RunOnceId: "DelMonkey"
Filename: "sc.exe"; Parameters: "stop Monkey64";      Flags: runhidden; RunOnceId: "StopMonkey64"
Filename: "sc.exe"; Parameters: "delete Monkey64";    Flags: runhidden; RunOnceId: "DelMonkey64"
Filename: "sc.exe"; Parameters: "stop WinDivert";     Flags: runhidden; RunOnceId: "StopWinDivert"
Filename: "sc.exe"; Parameters: "delete WinDivert";   Flags: runhidden; RunOnceId: "DelWinDivert"
Filename: "sc.exe"; Parameters: "stop WinDivert14";   Flags: runhidden; RunOnceId: "StopWinDivert14"
Filename: "sc.exe"; Parameters: "delete WinDivert14"; Flags: runhidden; RunOnceId: "DelWinDivert14"
Filename: "sc.exe"; Parameters: "stop WinDivert64";   Flags: runhidden; RunOnceId: "StopWinDivert64"
Filename: "sc.exe"; Parameters: "delete WinDivert64"; Flags: runhidden; RunOnceId: "DelWinDivert64"

[Code]

{ ---------------------------------------------------------------- }
{ Установка                                                        }
{ ---------------------------------------------------------------- }

{ Останавливает всё, что держит файлы установки.

  Без этого обновление поверх работающего net67 падает на
  exe\Monkey64.sys: WinDivert - драйвер режима ядра, и пока он загружен,
  Windows держит его файл открытым. Закрытие окна драйвер не выгружает. }
procedure StopRunningEngine();
var
  ResultCode: Integer;
  Names: array[0..4] of String;
  I: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/F /IM net67.exe /IM winws.exe /IM winws2.exe /IM amneziawg.exe',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  Names[0] := 'Monkey';
  Names[1] := 'Monkey64';
  Names[2] := 'WinDivert';
  Names[3] := 'WinDivert14';
  Names[4] := 'WinDivert64';
  for I := 0 to 4 do
  begin
    Exec(ExpandConstant('{sys}\sc.exe'), 'stop ' + Names[I], '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\sc.exe'), 'delete ' + Names[I], '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
  end;

  { Диспетчер служб отпускает файл не сразу после delete. }
  Sleep(2000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopRunningEngine();
end;

{ ---------------------------------------------------------------- }
{ Удаление                                                         }
{ ---------------------------------------------------------------- }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  ScriptPath: String;
begin
  { usUninstall - файлы приложения ещё на диске. Спрашиваем и чистим
    hosts именно здесь: после удаления звать будет нечего. }
  if CurUninstallStep = usUninstall then
  begin
    ScriptPath := ExpandConstant('{app}\tools\clear_hosts.ps1');
    if FileExists(ScriptPath) then
    begin
      if MsgBox('Удалить записи net67 из файла hosts?' + #13#10 + #13#10 +
                'Если оставить, сайты продолжат ходить через прописанные ' +
                'адреса. Ваши собственные записи в hosts не пострадают ' +
                'в любом случае.',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
             '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
             '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode <> 0 then
          MsgBox('Не удалось очистить hosts автоматически.' + #13#10 +
                 'Файл: %SystemRoot%\System32\drivers\etc\hosts' + #13#10 +
                 'Удалите блок между строками net67:hosts managed begin и end.',
                 mbInformation, MB_OK);
      end;
    end;
  end;

  if CurUninstallStep = usPostUninstall then
    MsgBox('Программа удалена.' + #13#10 + #13#10 +
           'Настройки, пресеты и списки остались в папке установки — ' +
           'при повторной установке они подхватятся. Если нужно убрать ' +
           'всё, удалите папку целиком.',
           mbInformation, MB_OK);
end;
