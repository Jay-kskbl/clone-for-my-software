# 本项目使用的 OpenSearch 镜像：官方镜像 + 官方中文分词插件 analysis-smartcn（附录 A13）。
#
# 两个索引的 mapping（backend/app/modules/text_index/mappings/）用到了这个插件提供的
# smartcn 分析器；没有它，创建索引会直接失败。
#
# analysis-smartcn 与 OpenSearch 同版本发布，安装时自动取与镜像一致的版本。
# 升级 OpenSearch 时只改这里的版本号（docker-compose.yml 通过 build 引用本文件）。
ARG OPENSEARCH_VERSION=2.19.1
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}

RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-smartcn
