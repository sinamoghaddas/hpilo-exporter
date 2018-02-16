FROM alpine:3.1
MAINTAINER IDNT
RUN apk add --update python py-pip
ADD . /usr/src/hpilo_exporter
RUN pip install -r /usr/src/hpilo_exporter/requirements.txt
RUN pip install -e /usr/src/hpilo_exporter
WORKDIR /usr/src/hpilo_exporter/src
ENTRYPOINT ["hpilo-exporter"]
EXPOSE 9416
