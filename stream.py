# Based on code shamelessly stolen from https://picamera.readthedocs.io/en/latest/recipes2.html#web-streaming

import io
import picamera
import logging
import socketserver
import configparser
from threading import Condition
from http import server
from string import Template

PAGE="""\
<html>
    <head>
        <title>$title</title>
    </head
    <body>
        <img src="stream.mjpg" width="$width" height="$height" />
    </body>
</html>
"""

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # this is a new frame, copy the existing buffer's content and notify all clients that it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path =='/':
            # redirect to index.html
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            # serve the web page containing the video stream
            d = dict(title=config.get('General', 'name'), \
                     width=config.get('Stream', 'resolution.width'), \
                     height=config.get('Stream', 'resolution.height'))
            content = Template(PAGE).substitute(d).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            # serve the mjpeg video stream
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning('Removed streaming client %s: %s', self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# set up the logger
logger = logging.getLogger('stream')
logger.setLevel('DEBUG')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

# read the config file
config = configparser.ConfigParser()
config.read('settings.ini')
logger.info('Initializing stream: ' + config.get('General', 'name'))

# start the camera rolling and the server listening on the configured port
resolutionString = config.get('Stream', 'resolution.width') + 'x' + config.get('Stream', 'resolution.height')
with picamera.PiCamera(resolution=resolutionString, framerate=24) as camera:
    output = StreamingOutput()
    camera.start_recording(output, format='mjpeg')
    try:
        address = ('', int(config.get('Stream', 'port')))
        server = StreamingServer(address, StreamingHandler)
        logger.info('Listening on port ' + config.get('Stream', 'port'))
        server.serve_forever()
    finally:
        camera.stop_recording()

