import socket
import re
from argparse import ArgumentParser

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
    def __init__(self, proxy_host, proxy_port, 
                 buffer_size: int = 1024, debug: bool = False):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.buffer_size = buffer_size
        self.past_host_list = []
        self.debug = debug

    def start(self):
        # bind socket to port and start listening
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.proxy_host, self.proxy_port))
            s.listen()
            print(f"listening on port {self.proxy_port}...")

            while True:
                # wait for a connection
                connection, address = s.accept()
                print(f"client {address} connected...")
                
                # set connection to alive
                live_connection = True

                # initialize a variable to store the last target host
                # we'll use this in cases where the client requests
                # additional files
                target_host = ''

                with connection as c:
                    # set a long timeout
                    # c.settimeout(10)
                    while live_connection:
                        # receive data from the connection
                        try:
                            rq_data = c.recv(self.buffer_size)

                            # if an empty byte-string was received, end the loop
                            print(rq_data)
                            if not rq_data:
                                print(f"client {address} disconnected...\n\n")
                                break
                            
                            # read the request and respond to it
                            client_rsp_data_list, target_host = self._respond_to_message([rq_data], target_host)
                            self.past_host_list.append(target_host)
                            print(f"start {target_host = }")
                            # if the client hasn't specified a target host (other than localhost)
                            # set the connection target host to the last targeted one
                            # if not target_host:
                            #     target_host = last_target_host

                            # send the response to the clients request
                            for rsp_data in client_rsp_data_list:
                                # close connection and end loop
                                if rsp_data == b'CLOSE':
                                    c.close()
                                    live_connection = False
                                else:
                                    # print('sending:\n', rsp_data)
                                    c.sendall(rsp_data)
                        
                        # if the socket times out, break the loop
                        except socket.timeout:
                            live_connection = False
    
    def _respond_to_message(self, raw_data_list: list, target_host: str):
        # get the first chunk of data since it should contain
        # the header
        header_data = raw_data_list[0]

        # parse the message then handle it and get its status type
        parsed_data = HttpParser(header_data, target_host)
        status, out_data = parsed_data.handle()
        print(f"{status} received...")

        # if an empty string was given as the target host
        # target the current parsed host
        if not target_host:
            print(f"overwrote original target host '{target_host}' with '{parsed_data.host}'")
            target_host = parsed_data.host

        # if the header contains an OK, respond to the client
        # with the full list of raw byte strings
        # if it exists, modify the 'Connection: close' string
        # to request a persistent connection
        if status == 'OK':
            rsp_data_list = self._modify_connection_type(raw_data_list)
        
        # otherwise if the message is a get (or redirect)
        # connect to the target host, get its response
        # and recursively call this function until we get an OK
        elif status == 'GET':
            rsp_data_list, target_host = self._respond_to_message(
                self._connect_to(
                    rq_data=out_data, 
                    host=target_host
                ), 
                target_host
            )
        
        # if we generated an error return it to the client and close the connection
        elif status == 'ERROR':
            # add a custom CLOSE bytestring to tell our script to
            # close the connection
            rsp_data_list = [out_data, b'', b'CLOSE']

        return rsp_data_list, target_host
    
    def _modify_connection_type(self, data_list):
        out_data_list = []
        replaced = False

        old_str = b'Connection: close'
        new_str = b'Connection: keep-alive'

        for byte_string in data_list:
            if not replaced and old_str in byte_string:
                # Replace the first instance of the substring and mark as replaced
                out_data_list.append(byte_string.replace(old_str, new_str))
                replaced = True
            else:
                # Append the byte-string as is if not the target for replacement
                out_data_list.append(byte_string)
        
        return out_data_list


    def _connect_to(self, rq_data, host: str, port: int = 80):
        rsp_list = []
        live_connection = True
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                print(f'connecting to {host}:{port}...')
                s.connect((host, port))
                s.sendall(rq_data)

                while live_connection:
                    rsp_data = s.recv(self.buffer_size)
                    # print(rsp_data)
                    rsp_list.append(rsp_data)
                    if not rsp_data:
                        live_connection = False

            return rsp_list

        except Exception as e:
            print(e)
        #     return self._connect_to(rq_data, self.past_host_list[-1])
                
            
        

class HttpParser:
    def __init__(self, data, target_host):
        self.raw = data
        self.dict = dict()

        self.target_host = target_host
        self.host = None

        # decode raw byte string using iso-8859-1 encoding then parse it
        self.string = self.raw.decode("iso-8859-1")
        self._parse_string()

    def handle(self):
        data_dict = self.dict.copy()
        message_type = data_dict.get('Message Type', None)

        # handle requests/responses differently
        if message_type == 'REQUEST':
            return self._handle_rq_message(data_dict)
        elif message_type == 'RESPONSE':
            return self._handle_rsp_message(data_dict)
        else:
            return 'ERROR', b'HTTP/1.0 400 Bad Request\r\n\r\n'
    
    def _parse_string(self):
        # split the decoded string along line breaks
        data_line_list = self.string.splitlines()
        
        # extract the first line of the request and parse it separately
        header_line = data_line_list.pop(0)

        # parse the data
        self._parse_header(header_line)

        # if the message isn't a 200 OK, parse the body too
        # (otherwise we can just forward it to the requesting client)
        if self.dict.get('Status Code', None) != '200':
            self._parse_body(data_line_list)

    def _parse_header(self, header_line: str):
        # split the header on whitespace
        header_chunk_list = re.split(' ', header_line, 2)
        
        # if the first element of the http message starts with 'http'
        # it's a response, otherwise treat it as a request
        if header_chunk_list[0].lower().startswith('http'):
            self._parse_rsp_header(header_chunk_list)
        else:
            self._parse_rq_header(header_chunk_list)

    def _parse_rq_header(self, header_chunk_list):
        """
        function to parse the header of an http request message
        """
        method, path, version = header_chunk_list
        self.dict['Message Type'] = 'REQUEST'
        self.dict['Method'] = method
        self.dict['Path'] = path
        self.dict['Version'] = version

    def _parse_rsp_header(self, header_chunk_list):
        """
        function to parse the header of an http response message
        """
        version, status_code, status = header_chunk_list
        self.dict['Message Type'] = 'RESPONSE'
        self.dict['Version'] = version
        self.dict['Status Code'] = status_code
        self.dict['Status'] = status

    def _parse_body(self, data_line_list: list):
        """
        function to parse the body of an http message
        only retains fields with the pattern "key: value"
        separated by "\r\n"
        """
        for data_line in data_line_list:
            # if line has contents
            if data_line:
                # try to split the data line on a colon
                # and skip it if there is no colon
                try:
                    field_name, field_val = re.split(':', data_line, 1)
                    # strip both of leading/trailing whitespace and add to the dict
                    self.dict[field_name.strip()] = field_val.strip()

                except ValueError:
                    continue
        
    def _handle_rq_message(self, data_dict):
        # return a client error if there's no previous target host
        # and they haven't specified a path to the proxy (or if they try to get the favicon.ico of localhost)
        valid_path_host = ~(data_dict.get('Host', '').lower().startswith("localhost")) |\
            ((data_dict.get('Path', '') != '/') &\
             (data_dict.get('Path', '') != '/favicon.ico'))
        
        if not self.target_host and not valid_path_host:
            return 'ERROR', b'HTTP/1.0 404 Not Found\r\n\r\n'

        # otherwise handle get
        elif data_dict.get('Method', None) == "GET":
            return self._handle_get(data_dict)
        
        else:
            # raise an error indicating this isn't implemented yet
            return 'ERROR', b'HTTP/1.0 501 Not Implemented\r\n\r\n'

    def _handle_rsp_message(self, data_dict):
        status_code = data_dict.get('Status Code', None)
        # if the message is an OK, return 'OK' to indicate the message
        # should be returned to the original client immediately
        if status_code == "200":
            return 'OK', None
        
        # otherwise handle redirects
        elif status_code == "301":
            print('redirecting traffic...')
            return self._handle_redirect(data_dict)

        # otherwise return an error indicating this isn't implemented yet
        else:
            return 'ERROR', b'HTTP/1.0 501 Not Implemented\r\n\r\n'

    def _handle_get(self, data_dict):
        """
        function to handle a get request, takes the path from the current
        request and reformats it to bounce it to its final destination
        """
        file_path = data_dict.get('Path')
        host = data_dict.get('Host')

        print(f"{file_path = }")
        print(f"{host = }")
        print(f"{self.target_host = }")

        page_refreshed = (file_path == '/' + self.target_host)

        # if the target host is defined, use it instead
        if self.target_host and not page_refreshed:
            host = self.target_host
        # otherwise if it starts with localhost reformat it
        # also address a failure case where the browser refreshes
        # and resends the full url on the same connection
        elif host.lower().startswith('localhost') | page_refreshed:
            print('reformatting GET request:')
            print(f"old path: {file_path}\nold host: {host}")
            file_path, host = self._reformat_path_host(file_path)
            print(f"new path: {file_path}\nnew host: {host}")

        return 'GET', self._bounce_get_rq(file_path, host)
    
    def _handle_redirect(self, data_dict):
        """
        function to handle a redirect response, takes the path from the
        reponse and reformats it to bounce a new get to its final destination
        """
        new_url = data_dict.get('Location')
        new_path, new_host = self._clean_redirect(new_url)
        return 'GET', self._bounce_get_rq(new_path, new_host)
    
    def _clean_redirect(self, url):
        # only keep characters to the right of "://"
        # if "://" is not present keep the original url
        match = re.search(r'://(.*)', url)
        cleaned_url = match.group(1) if match else url

        # find the index of the first "/"
        split_index = cleaned_url.find('/', 0)

        # split the string on the split index
        new_host = cleaned_url[:split_index]
        new_path = cleaned_url[split_index:]
        return new_path, new_host
    
    def _bounce_get_rq(self, new_path, new_host):
        # update the object destination host
        self.host = new_host
        return "GET {} HTTP/1.0\r\nHost: {}\r\n\r\n".format(new_path, new_host).encode()

    def _reformat_path_host(self, old_path):
        """
        """
        # add a slash to the end if it's missing
        if old_path[-1] != "/":
            old_path += "/"

        # find the index of the second "/"
        split_index = old_path.find('/', 1)

        # split the string on the split index
        new_host = old_path[1:split_index]
        new_path = old_path[split_index:]

        return new_path, new_host


if __name__ == "__main__":
    parser = ArgumentParser("basic_web_proxy")
    parser.add_argument(
        "--port",
        nargs='?',
        help="The port the proxy will listen on (generally 1024 - 65535)", 
        type=int, 
        default=7713
    )
    args = parser.parse_args()

    web_proxy = WebProxy("localhost", args.port)
    web_proxy.start()