import socket
import re
from argparse import ArgumentParser

class WebProxy:
    def __init__(self, proxy_host, proxy_port, 
                 buffer_size: int = 1024):
        # set proxy params
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.buffer_size = buffer_size

        # init a list to store our previous hosts in
        self.past_host_list = []

    def start(self):
        """
        function to start the web proxy. starts the listener and waits for an
        incoming connection.
        """
        # bind socket to port and start listening
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.proxy_host, self.proxy_port))
            s.listen()

            while True:
                # wait for a connection
                connection, _ = s.accept()
                
                self._handle_client(connection)
                
    def _handle_client(self, connection):
        """
        function to take the connection socket provided by s.accept and handle
        the client. the connection is closed after sending or receiving an empty
        byte string.
        """
        # set connection to alive
        live_connection = True

        with connection as c:
            while live_connection:
                # receive data from the connection
                rq_data = c.recv(self.buffer_size)
                # if an empty byte-string was received, end the loop
                if not rq_data:
                    break
                
                # read the request and respond to it
                client_rsp_data_list, target_host = self._respond_to_message([rq_data])
                self.past_host_list.append(target_host)

                # send the response to the clients request
                for rsp_data in client_rsp_data_list:
                    # close connection and end loop
                    c.sendall(rsp_data)
                    if not rsp_data:
                        live_connection = False
    
    def _respond_to_message(self, raw_data_list: list):
        """
        function to parse a message from a remote server then respond to it.
        OKs are returned (to be sent to the client), GETs are bounced until 
        they return an OK, and ERRORs are returned (to be sent to the client).
        """
        # get the first chunk of data since it *should* contain
        # the header
        header_data = raw_data_list[0]

        # check if the past host list is populated and choose the last
        # element as the previous host
        if self.past_host_list:
            previous_host = self.past_host_list[-1]
        else:
            previous_host = None

        # parse the data and get the message status, out data, and target host
        data_parser = HttpParser(header_data, previous_host)
        data_parser.parse()
        status, out_data = data_parser.handle()
        target_host = data_parser.host

        # if the header contains an OK, respond to the client
        # with the full list of raw byte strings
        if status == 'OK':
            rsp_data_list = raw_data_list

        # otherwise if the message is a get (or redirect)
        # connect to the target host, get its response
        # and recursively call this function until we get an OK
        elif status == 'GET':
            rsp_data_list, _ = self._respond_to_message(
                self._connect_to(
                    rq_data=out_data, 
                    host=target_host
                ), 
            )
        
        # else if we generated an error return it to the client
        elif status == 'ERROR':
            rsp_data_list = [out_data, b'']

        return rsp_data_list, target_host

    def _connect_to(self, rq_data, host: str, port: int = 80):
        """
        function to connect to a remote server on host with default port 80, 
        then send it the given request (rq_data) and retrieve its response.
        """
        rsp_list = []
        live_connection = True
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(rq_data)

            while live_connection:
                rsp_data = s.recv(self.buffer_size)
                rsp_list.append(rsp_data)
                if not rsp_data:
                    live_connection = False

        return rsp_list                


class HttpParser:
    def __init__(self, data, previous_host):
        self.raw = data
        self.dict = dict()

        self.previous_host = previous_host
        self.host = None
        self.string = None

    def parse(self):
        # decode raw byte string using iso-8859-1 encoding then parse it
        self.string = self.raw.decode("iso-8859-1")
        self._parse_string()

    def handle(self):
        """
        function to handle the raw http byte-string
        """
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
        """
        function to split the decoded string on line breaks,
        then extract the header line to parse it. if it's a 200 OK
        response we ignore the body (so we don't try to read hundreds
        of lines of data)
        """
        # split the decoded string along line breaks
        data_line_list = self.string.splitlines()
        
        # extract the first line of the request and parse it separately
        header_line = data_line_list.pop(0)
        self._parse_header(header_line)

        # if the message isn't a 200 OK, parse the body too
        # (otherwise we can just forward it to the requesting client)
        if self.dict.get('Status Code', None) != '200':
            self._parse_body(data_line_list)

    def _parse_header(self, header_line: str):
        """
        function to parse the header line of an HTTP message. parses
        as either a request (rq) or response (rsp) type message depending
        on the first header element.
        """
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
        """
        function to handle 'request'-type messages with a method (like GET or HEAD).
        only GET is implemented, and other methods will return the 501 Note Implemented
        error. Invalid GET requests for the root/favicon.ico of localhost receive a 404
        Not Found error.
        """
        # get an indicator variable to show whether the host is new or the last
        # should be reused
        new_host = data_dict.get('Sec-Fetch-Site', None) != 'same-origin'

        # return a client error if there's no previous target host
        # and they haven't specified a path to the proxy (or if they try to get the favicon.ico of localhost)
        valid_path_host = ~(data_dict.get('Host', '').lower().startswith("localhost")) |\
            ((data_dict.get('Path', '') != '/') &\
             (data_dict.get('Path', '') != '/favicon.ico'))
        
        if new_host and not valid_path_host:
            return 'ERROR', b'HTTP/1.0 404 Not Found\r\n\r\n'

        # otherwise handle get
        elif data_dict.get('Method', None) == "GET":
            return self._handle_get(data_dict, new_host)
        
        else:
            # raise an error indicating this isn't implemented yet
            return 'ERROR', b'HTTP/1.0 501 Not Implemented\r\n\r\n'

    def _handle_rsp_message(self, data_dict):
        """
        function to handle 'response'-type messages with a status code.
        only 200, 301, and 404 are implemented. other response messages
        will receive a 501 Not Implemented server error
        """
        status_code = data_dict.get('Status Code', None)
        # if the message is an OK, return 'OK' to indicate the message
        # should be returned to the original client immediately
        if status_code == "200":
            return 'OK', None
        
        if status_code == "404":
            return 'OK', None
        
        # otherwise handle redirects
        elif status_code == "301":
            return self._handle_redirect(data_dict)

        # otherwise return an error indicating this isn't implemented yet
        else:
            return 'ERROR', b'HTTP/1.0 501 Not Implemented\r\n\r\n'

    def _handle_get(self, data_dict, new_host: bool):
        """
        function to handle a get request, takes the path from the current
        request and reformats it to bounce it to its final destination
        """
        file_path = data_dict.get('Path')
        host = data_dict.get('Host')

        # if the host is new, reformat it
        if new_host:
            file_path, host = self._reformat_path_host(file_path)

        # otherwise use the last one
        else:
            host = self.previous_host

        return 'GET', self._bounce_get_rq(file_path, host)
    
    def _handle_redirect(self, data_dict):
        """
        function to handle a redirect response, takes the path from the
        reponse and reformats it to bounce a new GET to its final destination
        """
        new_url = data_dict.get('Location')
        new_path, new_host = self._clean_redirect(new_url)
        return 'GET', self._bounce_get_rq(new_path, new_host)
    
    def _clean_redirect(self, url):
        """
        function to take the url from the Location field of a redirect
        and parse it into a host and path (which can then be formatted into
        a GET request)
        """
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
        """
        function to format a bounced GET request and update the object host
        attribute with the hostname used
        """
        # update the object destination host
        self.host = new_host
        return "GET {} HTTP/1.0\r\nHost: {}\r\n\r\n".format(new_path, new_host).encode()

    def _reformat_path_host(self, old_path):
        """
        function to reformat the path and host based on the old path
        provided in the client > proxy request (only used when a new
        connection is established)
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
    # get a parser for command line args and add the port argument
    # default port is 7713
    parser = ArgumentParser("basic_web_proxy")
    parser.add_argument(
        "--port",
        nargs='?',
        help="The port the proxy will listen on (generally 1024 - 65535)", 
        type=int, 
        default=7713
    )
    args = parser.parse_args()

    # instantiate the proxy and start it
    web_proxy = WebProxy("localhost", args.port)
    web_proxy.start()