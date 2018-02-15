# HP iLO Metrics Exporter

Blackbox like exporter used to export HP Server Integrated Lights Out (iLO) metrics to Prometheus. ILO version 1 to 4 is supported.

### Gauges

Here are the status code of gauge
```
0 - OK
1 - Degraded
2 - Dead (Other)
```

### Output example

hpilo-exporter is using [hpilo] (https://seveas.github.io/python-hpilo/) to retrieve health information. A typical 
reponse from a health_at_a_glance call will look like:

```
health_at_a_glance:
  battery: {status: OK}
  bios_hardware: {status: OK}
  fans: {redundancy: Redundant, status: OK}
  memory: {status: OK}
  network: {status: Link Down},
  power_supplies: {redundancy: Redundant, status: OK}
  processor: {status: OK}
  storage: {status: Degraded}
  temperature: {status: OK}
  vrm: {status: Ok}
  drive: {status: Ok}
```

The returned output would be:
```
hpilo_battery{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_storage{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 1.0
hpilo_fans{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_bios_hardware{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_memory{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_power_supplies{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_processor{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_network{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 2.0
hpilo_temperature{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 0.0
hpilo_vrm{product_name="ProLiant DL380 Gen6",server_name="name.fqdn.domain"} 0.0
hpilo_drive{product_name="ProLiant DL380 Gen6",server_name="name.fqdn.domain"} 0.0
hpilo_firmware_version{product_name="ProLiant DL360 Gen9",server_name="name.fqdn.domain"} 2.5
```

### Installing

You can install exporter on the server directly or on separate machine.
To run, you must have `Python` and `pip` installed.

To install with `pip`:
```
pip install -e $HPILO_EXPORTER_DIR
```

Then just:
```
hpilo-exporter [--address=0.0.0.0 --port=9416 --endpoint="/metrics"]
```

### Requesting metrics

To request metrics you have to provide the ilo target. This can be done by providing
query arguments or by setting environemnt varaibles.

A request with query arguments will look like:

```
curl 'http://127.0.0.1:9416/metrics?ilo_host=127.0.0.1&ilo_port=443&ilo_user=admin&ilo_password=admin'
```

To specify the target using environment variables you have to define:

```
ILO_HOST=127.0.0.1
ILO_PORT=443
ILO_USER=admin
ILO_PASSWORD=admin
```

Now you can omit the query arguments on the metrics endpoint:

```
curl 'http://127.0.0.1:9416/metrics'
```

Any query argument will override the default provided on the environment.

### Caching

Requesting metrics from iLO is not exactly the fastet operation and prometheus may timeout
when trying to scrape the metrics endpoint. To work around this issue hpilo-exporter offers 
a cache mode. 

With the cache mode activated the first request will trigger requesting metrics from ilo 
in the background and you will receive an error response. As soon as the first background 
metrics collection completes, hpilo-exporter will answer with the last operations result and 
schedules a new background metrics collection if not already in progress.

To enable the cache mode you can pass

```
ilo_cached=true
```

with your query parameters or set the environment variable

```
ILO_CACHED=true
```


### Docker

Prebuild images are available from the docker repository:
```
idnt/hpilo-exporter:latest
```

To build the image yourself
```
docker build --rm -t hpilo-exporter .
```

To run the container
```
docker run -p 9416:9416 hpilo-exporter:latest
```

Passing argument to the docker run command:
```
docker run -p 9416:9416 hpilo-exporter:latest --port 9416 --ilo_user my_user --ilo_password my_secret_password
```

### Docker compose

Here is an example of Docker Compose deployment:

```yml
hpilo:
    image: my.registry/hpilo-exporter
    ports:
      - 9416:9416
    command:
      - '--port=9416'
    deploy:
      placement:
        constraints:
          - node.hostname == my_node.domain
```

### Kubernetes

A helm chart designed for openstack-helm deployments is available at [prometheus-helm-addons](https://github.com/IDNT/prometheus-helm-addons).

### Prometheus config

Assuming:
- the exporter is available on `http://hpilo:9416`
- you use same the port,username and password for all your iLO

```yml
- job_name: 'hpilo'
  scrape_interval: 1m
  params:
    ilo_port: ['443']
    ilo_user: ['my_ilo_user']
    ilo_password: ['my_ilo_password']
  static_configs:
    - targets:
      - ilo_fqdn.domain

  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_ilo_host
    - source_labels: [__param_ilo_host]
      target_label: ilo_host
    - target_label: __address__
      replacement: hpilo:8082  # hpilo exporter.
```


             