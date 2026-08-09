# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('C:\\Users\\User\\Downloads\\zapret-21.1.1.4\\zapret-21.1.1.4\\src\\blockcheck\\data', 'blockcheck\\data'), ('C:\\Users\\User\\Downloads\\zapret-21.1.1.4\\zapret-21.1.1.4\\src\\config\\config.json', 'config')],
    hiddenimports=['app.feature_facades.appearance', 'app.feature_facades.blockcheck', 'app.feature_facades.diagnostics', 'app.feature_facades.dns', 'app.feature_facades.dpi_settings', 'app.feature_facades.external', 'app.feature_facades.hosts', 'app.feature_facades.lists', 'app.feature_facades.logs', 'app.feature_facades.orchestra', 'app.feature_facades.presets', 'app.feature_facades.profile', 'app.feature_facades.program_settings', 'app.feature_facades.runtime', 'app.feature_facades.telegram_proxy', 'app.feature_facades.tray', 'app.feature_facades.updater', 'app.feature_facades.window_geometry', 'blockcheck.ui.page', 'configsets.ui.page', 'dns.ui.page', 'hosts.ui.page', 'log.ui.page', 'oneclick.deps', 'oneclick.plans', 'oneclick.runner', 'oneclick.ui.button', 'orchestra.ui.page', 'orchestra.ui.settings_page', 'presets.ui.common.preset_subpage_base', 'presets.ui.control.zapret1.page', 'presets.ui.control.zapret2.page', 'presets.ui.zapret1.user_presets_page', 'presets.ui.zapret2.user_presets_page', 'profile.ui.preset_setup_page', 'profile.ui.profile_order_page', 'profile.ui.profile_setup_page', 'settings.dpi.page', 'telegram_proxy.ui.page', 'ui.pages.about_page', 'ui.pages.support_page', 'updater.ui.page', 'vpn.ui.page', 'winws_log_analyzer.ui.page', 'wizard.apply', 'wizard.plans', 'wizard.ui.dialog'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='net67',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=['C:\\Users\\User\\Downloads\\zapret-21.1.1.4\\zapret-21.1.1.4\\ico\\net67.ico'],
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='net67',
)
