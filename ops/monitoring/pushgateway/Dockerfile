FROM prom/pushgateway:latest

USER nobody
ENTRYPOINT ["pushgateway"]
CMD ["--web.listen-address=:9091", "--persistence.file=/data/metrics", "--persistence.interval=30s"]
