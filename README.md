# Basic Web Proxy
#### Beatrice Brown-Mulry

## Introduction

This is a basic single-threaded web proxy implementation in Python as an exercise in HTTP and socket programming. Client requests are reformatted into HTTP/1.0, sent to the target host, then parsed and returned to the client.

## Usage
After the repository has been cloned, the script can be run with:
`python3 main.py --port PORTNUMBER` or `python3 main.py`

The default port number is 7713. The proxy has been tested extensively on http://gaia.cs.umass.edu and http://google.com, but will not work on sites that require HTTPS. 

URLs should be appended to localhost like the following:
`http://localhost:7713/gaia.cs.umass.edu`

## Errors
- **404 Not Found**: Will be returned if the client requests the root or favicon.ico of localhost.
- **501 Not Implemented**: Will be returned if the client sends a request which is not implemented (only GET requests and 200, 301, and 404 responses are implemented).
- **Other errors**: Will be returned from the destination server if applicable.
