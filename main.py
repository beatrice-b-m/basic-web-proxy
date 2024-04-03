import socket

"""
You will implement a simple web proxy. The proxy will take requests from the browser/- client,
parse the request, and send the request to the web server. The response gathered by the proxy will
be sent back to the browser. For this functionality, the proxy should open a socket connection on
startup, and listen for incoming requests. On getting a request from the browser, the proxy should
parse the HTTP request to determine the destination server, and open a connection to it. It should
then send the request, process the reply, and send it back to the browser. The port number for the
proxy should be a command line argument.

Your proxy only need to implement the HTTP GET request. If the browser/client is- sues other
HTTP requests like HEAD or POST, you can simply return a Not Implemented error message. For
simplicity you are allowed to use HTTP/1.0 between the proxy and the web server. There is no
need to implement the complex features of HTTP/1.1. If the browser sends a 1.1 request, you just
need to respond to the request, i.e. fetch the page corresponding to the GET request. Multi-thread
is also not required in this assignment, the proxy only needs to handle one client at the same time.

In order to verify your code, run the proxy program with specific port number then request a web
page from your browser. Direct the requests to the proxy program using your IP address and port
number. (e.g. http://localhost:8888/www.google.com)
"""

class WebProxy:
    def __init__(self, host, port):
        self.host = host
        self.port = port

        # reserve namespace
        self.socket = None

        self._establish_listener()

    def _establish_listener(self):
        # bind socket to port and start listening
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as self.socket:
            self.socket.bind((self.host, self.port))
            self.socket.listen()
            print(f"process listening on port {self.port}...")
            
            while True:
                connection, address = self.socket.accept()
                with connection:
                    print(f"connected established by {address}..!")
                    while True:
                        data = connection.recv(1024)
                        print(f"data received:\n{data}\n")
                        if not data:
                            break

                        connection.sendall(data)
            

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 7713

    web_proxy = WebProxy(HOST, PORT)