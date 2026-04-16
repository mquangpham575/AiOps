FROM prom/pushgateway:latest

# USER root removed because base image is scratch/minimal
# RUN apk add removed because apk is missing and not needed

COPY pushgateway.ini /etc/pushgateway.ini

USER nobody
ENTRYPOINT ["pushgateway"]
CMD ["--web.listen-address=:9091", "--persistence.file=/data/metrics", "--persistence.interval=30s"]
