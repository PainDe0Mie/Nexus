import sys, os, time, threading, configparser, json, subprocess, asyncio, backoff, requests
from aiohttp import web
from steam_web_api import Steam
from PyQt5.QtGui import QSurfaceFormat, QIcon
from PyQt5.QtCore import QTimer, QUrl, Qt, QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView,
    QWebEnginePage,
    QWebEngineSettings,
    QWebEngineProfile
)

os.environ['QTWEBENGINE_DISABLE_SANDBOX']   = '1'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']    = (
    '--autoplay-policy=no-user-gesture-required '
    '--disable-logging --enable-gpu-rasterization '
    '--enable-zero-copy --ignore-gpu-blacklist'
)                                                                                           

KEY         = "8E58F12CB6D12EE2B4309F4868E198F8"
CONFIG_PATH = "config.ini"
PORT        = 8000

class SteamWorker(QObject):
    finished = pyqtSignal(list)
    def __init__(self, steam_id, shared_session, api_key):
        super().__init__()
        self.steam_id = steam_id
        self.shared_session = shared_session
        self.api_key = api_key

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.HTTPError,
        max_tries=6,
        giveup=lambda e: 400 <= e.response.status_code < 500 and e.response.status_code != 429
    )
    def fetch_api(self, endpoint, params):
        url = f"https://api.steampowered.com/{endpoint}"
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def run(self):
        try:
            data = self.fetch_api(
                'IPlayerService/GetOwnedGames/v1/',
                {'key': self.api_key, 'steamid': self.steam_id, 'include_appinfo': True}
            )
            games_list = data.get('response', {}).get('games', [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print("Erreur : clé API Steam invalide.")  # :contentReference[oaicite:0]{index=0}
                self.finished.emit([])
                return
            else:
                raise

        results = []
        for g in games_list:
            appid = g['appid']
            try:
                detail = self.fetch_api(
                    'ISteamApps/GetAppDetails/v2/',
                    {'key': self.api_key, 'appids': appid}
                )
                desc = detail[str(appid)]['data'].get('short_description','').strip()
            except:
                desc = ''
            g['game_description'] = desc
            results.append(g)

        with open('local_games.json','w',encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False)

        self.finished.emit(results)

async def file_handler(request):
    fname = request.match_info.get('filename','index.html')
    return web.FileResponse(os.path.join(os.getcwd(), fname))

def start_http_server():
    app = web.Application()
    app.router.add_get('/{filename:.*}', file_handler)
    runner = web.AppRunner(app)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner,'127.0.0.1',PORT).start())
    loop.run_forever()

class MyPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, _type, isMainFrame):
        if url.scheme() == 'steam':
            app_id = url.path().lstrip('/').split('/')[-1]
            launch_steam_app(app_id)
            return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)

def launch_steam_app(app_id):
    steam_exe = os.path.join(
        os.environ.get("ProgramFiles(x86)",r"C:\Program Files (x86)"),
        "Steam","Steam.exe"
    )
    if not os.path.exists(steam_exe):
        steam_exe = "steam"
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    subprocess.Popen([steam_exe,"-silent"],startupinfo=si,creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(2)
    subprocess.Popen([steam_exe,"-applaunch",app_id],startupinfo=si,creationflags=subprocess.CREATE_NO_WINDOW)

class Browser(QMainWindow):
    def __init__(self, bg_flag):
        super().__init__()
        self.setWindowTitle("PS5 - Nexus")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.showFullScreen()

        fmt = QSurfaceFormat()
        fmt.setVersion(3,3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        QSurfaceFormat.setDefaultFormat(fmt)

        cache_dir = os.path.join(os.getcwd(),'cache')
        os.makedirs(cache_dir, exist_ok=True)
        profile = QWebEngineProfile('Default', self)
        profile.setCachePath(cache_dir)
        profile.setHttpCacheMaximumSize(100*1024*1024)
        profile.setPersistentStoragePath(cache_dir)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)

        self.view = QWebEngineView(self)
        self.view.setPage(MyPage(profile, self.view))
        self.setCentralWidget(self.view)

        base = f"http://127.0.0.1:{PORT}"
        self.view.load(QUrl(f"{base}/load.html?bg={int(bg_flag)}"))
        QTimer.singleShot(15000, lambda:
            self.view.load(QUrl(f"{base}/index.html?bg={int(bg_flag)}"))
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("nexus.ico"))

    cfg = configparser.ConfigParser(); cfg.read(CONFIG_PATH)
    worker = SteamWorker(cfg['STEAM']['id'], cfg['STEAM']['shared_session'].strip('"'), KEY)
    thread = QThread(); worker.moveToThread(thread)
    worker.finished.connect(lambda games: None)
    thread.started.connect(worker.run); thread.start()

    threading.Thread(target=start_http_server, daemon=True).start()

    browser = Browser(cfg['DATA'].getboolean('bg_games_music', True))
    browser.show()
    sys.exit(app.exec_())
