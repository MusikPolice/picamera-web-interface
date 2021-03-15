# Based on code shamelessly stolen from https://picamera.readthedocs.io/en/latest/recipes2.html#web-streaming

import io
import picamera
import logging
import socketserver
import configparser
import json
from threading import Condition
from http import server
from string import Template
from gpiozero import LED

PAGE="""\
<!DOCTYPE html PUBLIC"-//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <meta http-equiv="content-type" content="text/html; charset=utf-8" />
        <title>$title</title>
        <link rel="stylesheet" href="style.css" />
    </head
    <body>
        <script>
            /* 
             * To prevent Firefox FOUC, this must be here
             * See https://bugzilla.mozilla.org/show_bug.cgi?id=1404468
             */
            let FF_FOUC_FIX;

            function updateSettings() {
                var settings = {
                    brightness: document.getElementById('brightness-range').value,
                    ir: document.getElementById('ir-toggle').checked
                };
                var json = JSON.stringify(settings);
                fetch('/settings', {
                    method: 'post',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: json
                });
            }
        </script>

        <div id="content">
            <img src="stream.mjpg" width="$width" height="$height" />
            <div id="settings">
                <div id="brightness" class="center-vertical">
                    <span>Brightness: </span>
                    <input type="range" id="brightness-range" min="40" max="75" value="50" onchange="updateSettings();">
                </div>
                <div id="ir" class="center-vertical">
                    <span>Infrared: </span>
                    <label class="switch">
                        <input id="ir-toggle" type="checkbox" onchange="updateSettings()">
                        <span class="slider round"></span>
                    </label>
                </div>
            </div>
        </div>
    </body>
</html>
"""

CSS="""\
body {
    background: $color3;
}

img {
    max-width: $width;
    max-height: $height;
    width: 98%;
    height: auto;
    margin: 5px 1vw 5px 1vw;
    border: 3px solid #5E6472;
    border-radius: 10px;
}

#brightness {
    margin-left: 1vw;
    height: 40px;
    width: 98%;
}

#brightness span {
    color: #5E6472;
    font-family: verdana;
}

.center-vertical {
    display: flex;
    justify-content: left;
    align-items: center;
}

/* As it turns out, styling input ranges is a nightmare */
input[type=range] {
    width: 30%;
    margin: 10px;
    background-color: transparent;
    -webkit-appearance: none;
}
input[type=range]:focus {
    outline: none;
}
input[type=range]::-webkit-slider-runnable-track {
    background: $color2;
    border: 0.2px solid $color4;
    border-radius: 1.3px;
    width: 100%;
    height: 8.4px;
    cursor: pointer;
}
input[type=range]::-webkit-slider-thumb {
    margin-top: -11px;
    width: 15px;
    height: 30px;
    backgorund: $color1;
    border: 1px solid $color4;
    border-radius: 5px;
    cursor: pointer;
    -webkit-appearance: none;
}
input[type=range]:focus::-webkit-slider-runnable-track {
    background: #fdfbf3;
}
input[type=range]::-moz-range-track {
    background: $color2;
    border: 0.2px solid $color4;
    border-radius: 1.3px;
    width: 100%;
    height: 8.4px;
    cursor: pointer;
}
input[type=range]::-moz-range-thumb {
    width: 15px;
    height: 30px;
    background: $color1;
    border: 1px solid $color4;
    border-radius: 5px;
    cursor: pointer;
}
input[type=range]::-ms-track {
    background: transparent;
    border-color: transparent;
    border-width: 14.1px 0;
    color: transparent;
    width: 100%;
    height: 8.4px;
    cursor: pointer;
}
input[type=range]::-ms-fill-lower {
    background: #f7ebc7;
    border: 0.2px solid $color4;
    border-radius: 2.6px;
}
input[type=range]::-ms-fill-upper {
    background: $color2;
    border: 0.2px solid $color4;
    border-radius: 2.6px;
}
input[type=range]::-ms-thumb {
    width: 15px;
    height: 30px;
    background: $color1;
    border: 1px solid $color4;
    border-radius: 5px;
    cursor: pointer;
    margin-top: 0px;
    /*Needed to keep the Edge thumb centred*/
}
input[type=range]:focus::-ms-fill-lower {
    background: color2;
}
input[type=range]:focus::-ms-fill-upper {
    background: $color4;
}
@supports (-ms-ime-align:auto) {
    /* Pre-Chromium Edge only styles, selector taken from hhttps://stackoverflow.com/a/32202953/7077589 */
    input[type=range] {
        margin: 0;
        /*Edge starts the margin from the thumb, not the track as other browsers do*/
    }
}

/* style the IR toggle switch */
.switch {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 34px;
}

/* Hide default HTML checkbox */
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

/* The slider */
.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  -webkit-transition: .4s;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 26px;
  width: 26px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  -webkit-transition: .4s;
  transition: .4s;
}

input:checked + .slider {
  background-color: #2196F3;
}

input:focus + .slider {
  box-shadow: 0 0 1px #2196F3;
}

input:checked + .slider:before {
  -webkit-transform: translateX(26px);
  -ms-transform: translateX(26px);
  transform: translateX(26px);
}

/* Rounded sliders */
.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
}
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
            d = dict(title = config.get('General', 'name'), \
                     width = config.get('Stream', 'resolution.width'), \
                     height = config.get('Stream', 'resolution.height'))
            content = Template(PAGE).substitute(d).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/style.css':
            # serve the CSS stylesheet
            d = dict(width = config.get('Stream', 'resolution.width') + 'px', \
                     height = config.get('Stream', 'resolution.height') + 'px', \
                     color1 = config.get('Style', 'color1'), \
                     color2 = config.get('Style', 'color2'), \
                     color3 = config.get('Style', 'color3'), \
                     color4 = config.get('Style', 'color4'))
            content = Template(CSS).substitute(d).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/css')
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
    def do_POST(self):
        if self.path == '/settings':
            try :
                # parse request body json
                contentLength = int(self.headers.get('Content-Length'))
                request = json.loads(self.rfile.read(contentLength))
                logger.info('POST request from %s: %s', self.client_address, str(request))
                camera.brightness = int(request['brightness'])

                # infrared is backward - pulling the pin low turns it on
                # TODO: figure out how to flip the the pin to active low so this is nicer code
                if request['ir'] == True:
                    ir.off()
                else:
                    ir.on()

                # if everything worked, respond with a 200 OK
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                logger.error('Failed to process POST request from %s: %s', self.client_address, str(e))
                self.send_response(400)
                self.end_headers()
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

# initialize the camera - turn off IR mode
ir = LED(4)
ir.on()

# start the camera rolling and the server listening on the configured port
resolutionString = config.get('Stream', 'resolution.width') + 'x' + config.get('Stream', 'resolution.height')
with picamera.PiCamera(resolution=resolutionString, framerate=24) as camera:
    output = StreamingOutput()
    camera.start_recording(output, format='mjpeg')
    camera.brightness = 50
    try:
        address = ('', int(config.get('Stream', 'port')))
        server = StreamingServer(address, StreamingHandler)
        logger.info('Listening on port ' + config.get('Stream', 'port'))
        server.serve_forever()
    finally:
        camera.stop_recording()

