FROM prom/pushgateway:latest

USER root
RUN apk add --no-cache apache2-utils

COPY pushgateway.ini /etc/pushgateway.ini

USER nobody
ENTRYPOINT ["pushgateway"]
CMD ["--web.listen-address=:9091", "--persistence.file=/data/metrics", "--persistence.interval=30s"]
