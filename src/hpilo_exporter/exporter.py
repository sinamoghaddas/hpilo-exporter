"""
Pulls data from specified iLO and presents as Prometheus metrics
"""
from __future__ import print_function
from _socket import gaierror
import sys
import hpilo
import os
import ssl
import time
import threading
import prometheus_metrics
from BaseHTTPServer import BaseHTTPRequestHandler
from BaseHTTPServer import HTTPServer
from SocketServer import ThreadingMixIn
from prometheus_client import generate_latest, Summary
from urlparse import parse_qs
from urlparse import urlparse
import concurrent.futures as futures

def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# Create a metric to track time spent and requests made.
REQUEST_TIME = Summary(
    'request_processing_seconds', 'Time spent processing request')

ilo_tasks={}
ilo_cache={}
ilo_pool = futures.ThreadPoolExecutor(max_workers=2)

def iloGetMetrics(host, port, user, password):
    
	# this will be used to return the total amount of time the request took
	start_time = time.time()

	ilo = None
	ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
	# Sadly, ancient iLO's aren't dead yet, so let's enable sslv3 by default
	ssl_context.options &= ~ssl.OP_NO_SSLv3
	ssl_context.check_hostname = False
	ssl_context.set_ciphers(('ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
	    'DH+HIGH:ECDH+3DES:DH+3DES:RSA+AESGCM:RSA+AES:RSA+HIGH:RSA+3DES:!aNULL:'
        '!eNULL:!MD5'))
	try:
		ilo = hpilo.Ilo(hostname=host,login=user,password=password,port=port,timeout=10,ssl_context=ssl_context)
	except hpilo.IloLoginFailed:
		print_err("ILO login failed")
		return None
	except gaierror:
		print_err("ILO invalid address or port")
		return None
	except hpilo.IloCommunicationError as e:
		print_err(e)
		return None

	# get product and server name
	try:
		product_name = ilo.get_product_name()
	except:
		product_name = "Unknown HP Server"
    	
	try:
		server_name = ilo.get_server_name()
	except:
		server_name = ""
	    
	# get health at glance
	health_at_glance = ilo.get_embedded_health()['health_at_a_glance']
    
	if health_at_glance is not None:
		for key, value in health_at_glance.items():
			for status in value.items():
				if status[0] == 'status':
					gauge = 'hpilo_{}_gauge'.format(key)
				elif status[1].upper() == 'OK':
					prometheus_metrics.gauges[gauge].labels(product_name=product_name,
										server_name=server_name).set(0)
				elif status[1].upper() == 'Redundant':
					prometheus_metrics.gauges[gauge].labels(product_name=product_name,
										server_name=server_name).set(0)
				elif status[1].upper() == 'DEGRADED':
					prometheus_metrics.gauges[gauge].labels(product_name=product_name,
										server_name=server_name).set(1)
				else:
					prometheus_metrics.gauges[gauge].labels(product_name=product_name,
										server_name=server_name).set(2)

	# get firmware version
	fw_version = ilo.get_fw_version()["firmware_version"]
    
	# prometheus_metrics.hpilo_firmware_version.set(fw_version)
	prometheus_metrics.hpilo_firmware_version.labels(product_name=product_name,
							server_name=server_name).set(fw_version)

	# get the amount of time the request took
	REQUEST_TIME.observe(time.time() - start_time)

	# generate and publish metrics
	return generate_latest(prometheus_metrics.registry)

def iloSetResult(key, future):
	try:
        	ilo_cache[key] = future.result()
	except Exception as e:
		print_err(e)

def iloGetCached(host, port, user, password):
	key = host+':'+str(port)+':'+user
	task = ilo_tasks.get(key, None)
	metrics = ilo_cache.get(key, None)
    
	if task is None or task.done():
		ilo_tasks[key] = ilo_pool.submit(iloGetMetrics, host, port, user, password)
		ilo_tasks[key].add_done_callback(lambda f: iloSetResult(key, f))

	return metrics

class ForkingHTTPServer(ThreadingMixIn, HTTPServer):
	max_children = 30
	timeout = 30

class RequestHandler(BaseHTTPRequestHandler):
	"""
	Endpoint handler
	"""
	def return_error(self):
        	self.send_response(500)
	        self.end_headers()

	def do_GET(self):
		"""
		Process GET request
		:return: Response with Prometheus metrics
		"""
		# get parameters from the URL
		url = urlparse(self.path)
		# following boolean will be passed to True if an error is detected during the argument parsing
		error_detected = False
		query_components = parse_qs(urlparse(self.path).query)

		ilo_host = None
		ilo_port = None
		ilo_user = None
		ilo_password = None
		try:
			ilo_host = query_components.get('ilo_host', [''])[0] or os.environ['ILO_HOST']
			ilo_port = int(query_components.get('ilo_port', [''])[0] or os.environ['ILO_PORT'])
			ilo_user = query_components.get('ilo_user', [''])[0] or os.environ['ILO_USER']
			ilo_password = query_components.get('ilo_password', [''])[0] or os.environ['ILO_PASSWORD']
			ilo_cached = (query_components.get('ilo_cached', [''])[0] or os.environ.get('ILO_CACHED', '')) in ['true', '1', 't', 'y', 'yes']
		except KeyError as e:
			print_err("missing parameter %s" % e)
			self.return_error()
			error_detected = True

		if url.path == self.server.endpoint and ilo_host and ilo_user and ilo_password and ilo_port:
			metrics = None
			if ilo_cached:
				metrics = iloGetCached(ilo_host, ilo_port, ilo_user, ilo_password)
			else:
				metrics = iloGetMetrics(ilo_host, ilo_port, ilo_user, ilo_password)
	
			if metrics is None:
				self.return_error()
				return

			self.send_response(200)
			self.send_header('Content-Type', 'text/plain')
			self.end_headers()
			self.wfile.write(metrics)

		elif url.path == '/':
			self.send_response(200)
			self.send_header('Content-Type', 'text/html')
			self.end_headers()
			self.wfile.write("""<html>
				<head><title>HP iLO Exporter</title></head>
				<body>
					<h1>HP iLO Exporter</h1>
					<p>Visit <a href="/metrics">Metrics</a> to use.</p>
				</body>
				</html>""")

		else:
			if not error_detected:
				self.send_response(404)
			self.end_headers()

class ILOExporterServer(object):
	"""
	Basic server implementation that exposes metrics to Prometheus
	"""

	def __init__(self, address='0.0.0.0', port=8080, endpoint="/metrics"):
		self._address = address
		self._port = port
		self.endpoint = endpoint

	def print_info(self):
		print_err("Starting exporter on: http://{}:{}{}".format(self._address, self._port, self.endpoint))
		print_err("Press Ctrl+C to quit")

	def run(self):
		self.print_info()

		server = ForkingHTTPServer((self._address, self._port), RequestHandler)
		server.endpoint = self.endpoint

		try:
			while True:
				server.handle_request()
		except KeyboardInterrupt:
			print_err("Killing exporter")
			server.server_close()
			ilo_pool.shutdown(False)

