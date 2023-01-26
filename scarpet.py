import sublime
import sublime_plugin

from pathlib import Path
import re

VERSION = "1.2.0"
PLATFORM = sublime.platform()

PACKAGE_FOLDER = Path(sublime.packages_path(), 'User', 'Scarpet')
PACKAGE_SCHEME_FOLDER = PACKAGE_FOLDER/'Schemes'
TEMPLATE_SCHEME = PACKAGE_SCHEME_FOLDER/'ScarpetTemplate.sublime-color-scheme'
PROG = re.compile(r'#[0-9A-F]{6}')

SCARPET_SETTINGS = None
DISABLE_PLUGIN = True
DISABLE_HEXCODE_REALIZATION = True
DISABLED_SYNTAX = []

def update_settings():
    global DISABLE_PLUGIN, DISABLE_HEXCODE_REALIZATION, DISABLED_SYNTAX
    DISABLE_PLUGIN = SCARPET_SETTINGS.get('disable_plugin', True)
    DISABLE_HEXCODE_REALIZATION = SCARPET_SETTINGS.get('disable_hexcode_realization', True)
    DISABLED_SYNTAX = SCARPET_SETTINGS.get('disabled_syntax', [])

class HexColorSchemeWriter:
    HEAD = b'{"author": "auto-generated by SublimeScarpetSyntax","variables": {"transparent": "rgba(1,22,38, 0.1)"},"rules":[\n'
    TAIL = b']}'
    ENTRY_FMT = '{{"scope":"region.{0:s}.string-format.scarpet","foreground":"{0:s}","background":"var(transparent)"}},\n'
    def __init__(self):
        self._scheme = None
        self._file = None
        self._entries = set()
        self._raw_count = 0
    def set_scheme(self, scheme: Path):
        if scheme == self._scheme:
            return
        self._scheme = scheme
        file = PACKAGE_FOLDER/self._scheme.name
        if self._file is None:
            self._file = file
            self.write_file()
        else:
            self._file.rename(file)
        self._file.rename(file)
    def write_file(self) -> None:
        with self._file.open('wb') as f:
            f.writelines((self.HEAD, self.TAIL))
    def write_entry(self, hexcode) -> None:
        if hexcode in self._entries:
            return
        self._entries.add(hexcode)
        self._raw_count += 1
        with self._file.open('r+b') as f:
            f.seek(-2, 2)
            f.writelines((bytes(self.ENTRY_FMT.format(hexcode), 'ASCII'), self.TAIL))
    def cleanup(self, hexcodes) -> None:
        if self._raw_count < 100:
            return
        if len(self._entries.difference(hexcodes)) > 100:
            self.write_file()
            self._entries.clear()
            self._raw_count = 0
    def full_clean(self):
        for f in PACKAGE_FOLDER.glob('*.sublime-color-scheme'):
            f.unlink()

HEX_COLOR_SCHEME_WRITER = HexColorSchemeWriter()

def current_scheme() -> Path:
    return Path(sublime.find_resources(sublime.ui_info()['color_scheme']['value'])[0])

class ScarpetEventListener(sublime_plugin.EventListener):
    def on_init(self, views: 'list[sublime.View]'):
        for view in views:
            view.run_command('scarpet')
            view.settings().add_on_change('scarpet.syntax', lambda: view.run_command('scarpet'))
            self._apply_hexcode_colors(view)

    def on_load_async(self, view: sublime.View):
        self._apply_hexcode_colors(view)

    def on_modified_async(self, view: sublime.View):
        self._apply_hexcode_colors(view)

    def on_exit(self):
        _plugin_unloaded()

    def _get_hexcode_regions(self, view: sublime.View) -> 'list[sublime.Region]':
        d = {}
        for fmt_r in view.find_by_selector('constant.other.hex-code.string-format.scarpet'):
            hexcode = PROG.findall(view.substr(fmt_r))[-1]
            str_r = view.expand_to_scope(fmt_r.b+1, 'region.arbitrary.string-format.scarpet')
            if str_r is not None:
                d.setdefault(hexcode, []).append(str_r)
        return d

    def _apply_hexcode_colors(self, view: sublime.View):
        if DISABLE_HEXCODE_REALIZATION:
            return
        hexcode_regions = self._get_hexcode_regions(view)
        for hexcode, regions in hexcode_regions.items():
            HEX_COLOR_SCHEME_WRITER.write_entry(hexcode)
            # view.erase_regions(hexcode)
            view.add_regions(hexcode, regions,
                scope='region.{:s}.string-format.scarpet'.format(hexcode),
                flags=sublime.PERSISTENT)
        HEX_COLOR_SCHEME_WRITER.cleanup(hexcode_regions.keys())

class ScarpetCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        if DISABLE_PLUGIN:
            return
        if self.view.settings().get('syntax') in DISABLED_SYNTAX:
            return
        scheme = current_scheme()
        self.create_scheme(scheme)
        if DISABLE_HEXCODE_REALIZATION:
            return
        HEX_COLOR_SCHEME_WRITER.set_scheme(scheme)

    @staticmethod
    def create_scheme(current_scheme: Path) -> Path:
        if PLATFORM != 'windows':
            ScarpetCommand._create_scheme_link(current_scheme)
        else:
            ScarpetCommand._create_scheme_file(current_scheme)

    @staticmethod
    def _create_scheme_link(current_scheme: Path) -> Path:
        scheme_link = PACKAGE_SCHEME_FOLDER/current_scheme.name

        if not scheme_link.exists():
            scheme_link.symlink_to(TEMPLATE_SCHEME.resolve())
        return scheme_link

    @staticmethod
    def _create_scheme_file(current_scheme: Path) -> Path:
        scheme_file = PACKAGE_SCHEME_FOLDER/current_scheme.name

        if not scheme_file.exists():
            scheme_content = sublime.load_resource(str('Packages'/TEMPLATE_SCHEME))
            with scheme_file.open('w') as scheme_f:
                scheme_f.write(scheme_content)
        return scheme_file


def clean_scheme_folder():
    for scheme_f in filter(TEMPLATE_SCHEME.__ne__, PACKAGE_SCHEME_FOLDER.iterdir()):
        scheme_f.unlink()

def _plugin_loaded():
    if not TEMPLATE_SCHEME.exists():
        if not PACKAGE_FOLDER.exists():
            PACKAGE_FOLDER.mkdir()
        if not PACKAGE_SCHEME_FOLDER.exists():
            PACKAGE_SCHEME_FOLDER.mkdir()
        scheme_content = sublime.load_resource('Packages/Scarpet/ScarpetTemplate.sublime-color-scheme')
        with TEMPLATE_SCHEME.open('w') as scheme_f:
            scheme_f.write(scheme_content)

def _plugin_unloaded():
    HEX_COLOR_SCHEME_WRITER.full_clean()
    clean_scheme_folder()

def plugin_loaded():
    global SCARPET_SETTINGS
    SCARPET_SETTINGS = sublime.load_settings('scarpet.sublime-settings')
    update_settings()
    SCARPET_SETTINGS.add_on_change('scarpet_settings_change', update_settings)
    sublime.set_timeout_async(_plugin_loaded)

def plugin_unloaded():
    sublime.set_timeout_async(_plugin_unloaded)