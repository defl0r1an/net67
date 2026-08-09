# Сторонние лицензии

net67 собран из чужих частей, и почти каждая приходит со своими
условиями. Здесь перечислено всё, что попадает в собранное приложение
или в этот репозиторий.

Файл нужен не для порядка ради порядка: часть условий требует
сохранять уведомления при распространении, а одно — PyQt6 — влияет на
то, под какой лицензией может выходить сам net67. Об этом ниже
отдельно.

---

## Требует решения: PyQt6

**Это единственный пункт, который нельзя закрыть правкой файла.**

PyQt6 распространяется на выбор: по GPL v3 либо по платной
коммерческой лицензии Riverbank. Третьего варианта нет.

Из этого следует одно из двух.

Либо net67 выходит под **GPL v3** — тогда исходники обязаны быть
открыты (они и так открыты), а условие выполнено само собой.

Либо у компании есть **коммерческая лицензия Riverbank** — тогда
ограничений на лицензию net67 нет.

Пока выбор не сделан, в корне нет файла `LICENSE`, и это осознанно:
объявить лицензию, а потом её поменять — хуже, чем не объявлять.
Проставить лицензию за вас я не могу, это решение владельца продукта.

Замечание: библиотека `PyQt6-Fluent-Widgets` (qfluentwidgets) идёт под
GPL v3 в бесплатной версии, то есть тянет за собой то же условие.

---

## Исходный проект — GUI zapret

net67 вырос из графической оболочки проекта zapret. Оболочка
распространялась под MIT.

MIT требует сохранять уведомление об авторских правах при
распространении. Уведомление должно лежать в файле `LICENSE` в корне —
**его там сейчас нет**, и это надо закрыть до публикации: текст
уведомления с именем правообладателя есть в исходном репозитории, из
которого взята оболочка. Придумывать имя правообладателя я не стал.

---

## Движок обхода — zapret (winws)

Автор: **bol-van**. Исходники: <https://github.com/bol-van/zapret> и
сборка под Windows <https://github.com/bol-van/zapret-win-bundle>.

В net67 попадают `winws.exe`, `winws2.exe` и наборы стратегий. Авторство
в файлах стратегий сохранено намеренно — строки `# AUTHOR: bol-van` и
`author = bol-van` в `src/presets/builtin/` и
`src/profile/strategy_catalogs/` трогать нельзя.

Проект распространяется под MIT.

---

## WinDivert

Перехват пакетов, без которого движок не работает. Файлы `WinDivert.dll`
и драйвер `.sys`.

Автор: **Basil Fierz**, <https://github.com/basil00/WinDivert>.
Лицензия: **LGPL v3** либо GPL v2 на выбор.

LGPL позволяет использовать библиотеку в закрытой программе при условии,
что её саму можно заменить, — у нас это обычная DLL рядом с
исполняемым файлом, условие выполняется.

---

## AmneziaWG

Клиент, поднимающий туннель на странице VPN: `amneziawg.exe`, `awg.exe`,
`wintun.dll`.

Проект: <https://github.com/amnezia-vpn/amneziawg-windows-client>,
основан на WireGuard for Windows (Copyright © 2018-2021 WireGuard LLC).
Лицензия: **MIT**.

`wintun.dll` — отдельный компонент от WireGuard LLC со своей лицензией,
разрешающей распространение в составе программ.

---

## Xray-core

Ядро, поднимающее подключение по ссылкам vless, vmess, trojan и ss:
`xray.exe`.

Проект: <https://github.com/XTLS/Xray-core>.
Лицензия: **MPL 2.0**.

MPL требует, чтобы изменения в самом ядре оставались открытыми. Мы ядро
не меняем — кладём готовый исполняемый файл, — поэтому от net67
требуется только сохранить уведомление и указать, где взять исходники.
Указано выше.

---

## Оформление — Nora

Палитра, пропорции панели, скругления и отступы перенесены из
музыкального плеера Nora.

Сам код Nora не используется: она написана на Electron с React и
Tailwind, net67 — на Python с PyQt6. Перенесены значения, а не
исходники. Уведомление сохранено, потому что MIT требует сохранять его
при использовании программы или существенных её частей, и дешевле
выполнить требование, чем спорить, где проходит граница.

Название «Nora» и упоминания её автора в интерфейсе net67 не
показываются: продукт другой, и вводить людей в заблуждение незачем.
Требование лицензии касается уведомления об авторских правах, а не
названия продукта.

```
MIT License

Copyright (c) 2023 Sandakan Nipunajith

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Шрифт знака — Barlow Condensed

Значок приложения набран начертанием Barlow Condensed ExtraBold.
Автор: **Jeremy Tribby**. Лицензия: **SIL Open Font License 1.1**.

Сам файл шрифта в репозиторий не кладётся: OFL накладывает условия на
распространение шрифта, а нам он нужен только на сборке значка.
`scripts/build_icon.py` принимает путь к нему ключом `--font`, скачать
можно с Google Fonts.

В готовом `.ico` лежат уже отрисованные пиксели — это результат работы
шрифта, а не сам шрифт, и OFL такое разрешает.

---

## Значки интерфейса — QtAwesome

Значки сервисов в редакторе hosts и на страницах берутся из QtAwesome,
который поставляет Font Awesome Free (**CC BY 4.0** для значков,
**SIL OFL 1.1** для шрифта) и Material Design Icons (**Apache 2.0**).

Сама обвязка QtAwesome — **MIT**.

---

## Остальные библиотеки Python

Ставятся из PyPI по `requirements-runtime.txt`, в репозиторий не
попадают, но попадают в собранное приложение.

| Библиотека | Лицензия |
|---|---|
| PyQt6, PyQt6-Qt6, PyQt6-sip | GPL v3 либо коммерческая (см. выше) |
| PyQt6-Fluent-Widgets | GPL v3 либо коммерческая |
| PyQt6-Frameless-Window | GPL v3 |
| QtAwesome | MIT |
| requests, urllib3, certifi | Apache 2.0 / MIT |
| PySocks | BSD |
| httpx | BSD |
| pywin32 | PSF |
| packaging | Apache 2.0 либо BSD |

Сборщики (PyInstaller — GPL с исключением для собранных программ,
Nuitka — Apache 2.0) в приложение не попадают.

---

## Что нужно сделать до публикации

1. Выбрать лицензию net67 с оглядкой на PyQt6 и положить `LICENSE`
   в корень.
2. Добавить туда же уведомление MIT исходного проекта — с именем
   правообладателя из репозитория, откуда взята оболочка.
3. Решить, попадают ли в публичный репозиторий бинарники движка
   (`winws.exe`, `WinDivert.dll`, драйвер). Сейчас они исключены
   в `.gitignore`, и сборка на GitHub без них соберёт интерфейс,
   которому нечего запускать.
