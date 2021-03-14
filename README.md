# picamera-web-interface
A simple web-based interface that streams live video from a Raspberry Pi.

This code borrows heavily from example code published in the [PiCamera documentation](https://picamera.readthedocs.io/en/latest/recipes2.html#web-streaming).

## Dependencies
Before you can get started, you'll need to make sure that you have both Python 3 and the PiCamera Python module installed:
```
sudo apt-get install python3 python3-picamera
```

## Configuration
There are a few options that can be configured in a file called `settings.ini`. Here are some default values:
```
[General]
name: The name of this camera

[Stream]
port: 8080
resolution.width: 640
resolution.height: 480
```

A few notes:
* `port` must be a value greater than 1024
* `resolution.width` and `resolution.height` must be set to one of [PiCamera's supported resolutions](https://picamera.readthedocs.io/en/release-1.3/fov.html#camera-modes).
