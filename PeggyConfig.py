
import network
import uasyncio, usocket
import json
import time
import random
import os
import gc
import socket
from uasyncio import core

gc.threshold(50000) # setup garbage collection

status_message_map = {
  200: "OK", 201: "Created", 202: "Accepted", 
  203: "Non-Authoritative Information", 204: "No Content",
  205: "Reset Content", 206: "Partial Content", 300: "Multiple Choices",
  301: "Moved Permanently", 302: "Found", 303: "See Other",
  304: "Not Modified", 305: "Use Proxy", 306: "Switch Proxy",
  307: "Temporary Redirect", 308: "Permanent Redirect",
  400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
  404: "Not Found", 405: "Method Not Allowed", 406: "Not Acceptable",
  408: "Request Timeout", 409: "Conflict", 410: "Gone",
  414: "URI Too Long", 415: "Unsupported Media Type", 
  416: "Range Not Satisfiable", 418: "I'm a teapot",
  500: "Internal Server Error", 501: "Not Implemented"
}

REDIRECT_URLS = [
    b'GET / HTTP/1.1\r\n',
    b'GET /redirect HTTP/1.1\r\n',
    b'GET /connecttest.txt HTTP/1.1\r\n',
    b'GET /generate_204 HTTP/1.1\r\n',
    b'GET /generate204 HTTP/1.1\r\n'
]

html_file = open('index_min.html','r')
html = html_file.read()
html_file.close()
cred_out = "PC_CREDENTIALS"
class PeggyConfig:
    #### PRIVATE ####

    def __init__(self, essid=None, save_credentials=True, pw_protected=False, pw="temp1234"):
        self.sta_if = network.WLAN(network.STA_IF)
        self.ap_if = network.WLAN(network.AP_IF)

        if essid is None:
            essid = "PeggyConfig_" + str(random.randint(0,255))

        self.essid = essid
        self.dns_server = None
        self.http_server = None
        self.ip = None
        self.socket = None
        self.server_port = 80
        self.dns_port = 53
        self.server_host = "0.0.0.0"
        self.save_credentials = save_credentials
        self.available_connections = []
        self.enable_pw = pw_protected
        self.pw = pw
        self.load_page = False
        self.success = False
    
    def _init_ap(self):
        print("Initializing Access Point.")
        self.ap_if.active(True)
        if self.enable_pw:
            self.ap_if.config(essid=self.essid, authmode=network.AUTH_WPA_WPA2_PSK, password=self.pw) 
        else:
            self.ap_if.config(essid=self.essid, authmode=network.AUTH_OPEN)
        self.ip = str(self.ap_if.ifconfig()[0])
        print("Hosting AP: " + self.essid)

    def _dinit_ap(self):
        print("Disabling Access Point.")
        self.ap_if.active(False)

    def _do_scan(self):
        self.available_connections = []
        self.sta_if.active(True)
        wifi_near = self.sta_if.scan()
        for conn in wifi_near:
            if (conn[0] == b'') or (conn[0].decode() == self.essid):
                continue
            self.available_connections.append(conn[0].decode('utf-8'))
            
    def _do_connect(self, ssid, pw):
        attempt = 0
        try:
            print("TRYING: " + ssid + " PW: " + pw)
            if self.sta_if.active() and self.sta_if.isconnected():
                self.sta_if.disconnect()
                time.sleep(0.5)
            
            self.sta_if.active(True)
            time.sleep(0.5)
            self.sta_if.connect(ssid,  pw)
            while not self.sta_if.isconnected():
                if attempt > 20:
                    self.sta_if.active(False)
                    time.sleep(0.5)
                    return False
                else:
                    time.sleep(1)
                    attempt = attempt + 1
                    pass
            return True
        except Exception as e:
            print("caught exception")
            print(e)
            self.sta_if.active(False)
            time.sleep(0.5)
            return False

    async def _dns_handler(self, socket, ip_address):
        print("DNS_HANDLER")
        while True:
            try:
                yield uasyncio.core._io_queue.queue_read(socket)
                request, self.client = socket.recvfrom(256)
                response = request[:2] # request id
                response += b"\x81\x80" # response flags
                response += request[4:6] + request[4:6] # qd/an count
                response += b"\x00\x00\x00\x00" # ns/ar count
                response += request[12:] # original request body
                response += b"\xC0\x0C" # pointer to domain name at byte 12
                response += b"\x00\x01\x00\x01" # type and class (A record / IN class)
                response += b"\x00\x00\x00\x3C" # time to live 60 seconds
                response += b"\x00\x04" # response length (4 bytes = 1 ipv4 address)
                response += bytes(map(int, ip_address.split("."))) # ip address parts
                socket.sendto(response, self.client)
                print("Client " + str(self.client))
            except Exception as e:
                print(e)

    async def _web_server(self):
        loadPage = False
        postRcvd = False
        while True: #Try & Except for creating socket.
            try:
                host = socket.getaddrinfo("0.0.0.0", 80)[0] 
                s = socket.socket()
                s.setblocking(True)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(host[-1])
                s.listen(5)
                break
            except Exception as e:
                print("Failed trying again...")
                print(e)
                time.sleep(0.25)
        while True:
            try:
                while True:
                    try:
                        yield core._io_queue.queue_read(s)
                    except core.CancelledError:
                        # Shutdown server
                        s.close()
                        return
                    try:
                        cl, addr = s.accept()
                    except:
                        # Ignore a failed accept
                        continue
                    cl_file = cl.makefile('rwb', 0)
                    time.sleep(0.1)
                    line = cl_file.readline()
                    response = None
                    isValid = False
                    print(line)
                    if line in REDIRECT_URLS:
                        loadPage = True
                        isValid = True
                    elif line == b'GET /AvailableWifi HTTP/1.1\r\n':
                        self._do_scan()
                        cl.send(";".join(self.available_connections))
                        loadPage = False
                        isValid = True
                    elif line == b'POST /dataIn HTTP/1.1\r\n':
                        print("GOT POST")
                        isValid = True
                        postRcvd = True
                    if isValid == False:
                        cl.close()
                        continue
                    cl_file = cl.makefile('rwb', 0)
                    while True:
                        line = cl_file.readline()
                        request = str(line)
                        if request.find('Content-Length:') != -1:
                            clStart = request.find('Content-Length:')
                            clEnd = len(request)-5
                            contentLength = int(request[clStart+16:clEnd])
                        if not line or line == b'\r\n':
                            if postRcvd == True:
                                data = cl.recv(contentLength)
                                postRcvd = False
                                credentials = json.loads(data)
                                self.success = self._do_connect(credentials["SSID"], credentials["PASSWORD"])
                                status_message = status_message_map.get(200, "Unknown")
                                cl.send(f"HTTP/1.1 {200} {self.success}\r\n".encode("ascii"))
                                if self.success and self.save_credentials:
                                    file = open(cred_out,'w')
                                    file.write(data)
                                    file.close()    
                            break
                    #program sends html file.
                    if loadPage == True:
                        response = html
                        #sends HTML and closes client.
                        response = (response,)
                        body = response[0]
                        status = response[1] if len(response) >= 2 else 200
                        content_type = response[2] if len(response) >= 3 else "text/html"
                        response = Response(body, status=status)
                        response.add_header("Content-Type", content_type)
                        if hasattr(body, '__len__'):
                            response.add_header("Content-Length", len(body))
                        
                        # write status line
                        status_message = status_message_map.get(response.status, "Unknown")
                        cl.send(f"HTTP/1.1 {response.status} {status_message}\r\n".encode("ascii"))

                        # write headers
                        for key, value in response.headers.items():
                            cl.send(f"{key}: {value}\r\n".encode("ascii"))

                        # blank line to denote end of headers
                        cl.send("\r\n".encode("ascii"))
                        cl.send(response.body)
                        cl.close()
                        loadPage = False
                        if self.success:
                            self._clean_up()
                            break;
                    else:
                        cl.close()

            except Exception as e:
                # s.close()
                cl.close()
                print('Error')
                print(e)

    def _run_catchall(self):
        self.socket = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        self.socket.setblocking(True)
        self.socket.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
        self.socket.bind(usocket.getaddrinfo(self.ip, self.dns_port, 0, usocket.SOCK_DGRAM)[0][-1])

        self.dns_server  = uasyncio.get_event_loop()
        self.dns_server.create_task(self._dns_handler(self.socket, self.ip))

    def _run_server(self):
        print("Starting Web Server.")
        self.http_server = uasyncio.get_event_loop()
        self.http_server.create_task(self._web_server())
        self.http_server.run_forever()
        
    def _clean_up(self):
        try:
            self._dinit_ap()
            self.dns_server.stop()
            self.dns_server.cancel()
            self.socket.close()
            self.http_server.stop()
            self.http_server.cancel()
        except:
            print("Error Cleaning Up")

    #### PUBLIC ####
    def doConfig(self):
        self._init_ap()
        self._run_catchall()
        self._run_server()
        return self.success

class Response:
    def __init__(self, body, status=200, headers={}):
        self.status = status
        self.headers = headers
        self.body = body

    def add_header(self, name, value):
        self.headers[name] = value

    def __str__(self):
        return f"""\
    status: {self.status}
    headers: {self.headers}
    body: {self.body}"""
