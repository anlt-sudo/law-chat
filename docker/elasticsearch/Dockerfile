# Elasticsearch + plugin analysis-icu (tách từ tiếng Việt, dùng cho analyzer vi_standard / vi_folded – F07 §6.1)
ARG ES_VERSION=8.15.3
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}
RUN bin/elasticsearch-plugin install --batch analysis-icu
