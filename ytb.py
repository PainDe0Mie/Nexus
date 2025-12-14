#!/usr/bin/env python3
import json
import webbrowser
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from youtubesearchpython import Search
from yt_dlp import YoutubeDL
from functools import lru_cache

PORT = 8000

@lru_cache(maxsize=128)
def search_best_music_url(game_name):
    query = f'"{game_name}" theme main menu home screen "music" ps5'
    results = Search(query, language='fr', region='FR').result()['result']
    if not results:
        return None
    video_url = results[0]['link']

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return info['url']

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/search_music/'):
            game_name = unquote(self.path[len('/search_music/'):])
            try:
                mp3_url = search_best_music_url(game_name)
                payload = {'mp3_url': mp3_url}
                status = 200
            except Exception as e:
                payload = {'mp3_url': None, 'error': str(e)}
                status = 500
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        else:
            try:
                super().do_GET()
            except (ConnectionResetError, BrokenPipeError):
                pass

if __name__ == '__main__':
    server = ThreadingHTTPServer(('', PORT), Handler)
    print(f" http://localhost:{PORT}")
    webbrowser.open(f'http://localhost:{PORT}/index.html')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
        server.server_close()
