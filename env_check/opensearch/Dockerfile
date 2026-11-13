# 环境实测用的 OpenSearch 镜像：官方镜像 + 中文分词插件
#
# 版本说明：OPENSEARCH_VERSION 默认值请在构建前到 https://opensearch.org/downloads 确认，
# 并把最终使用的版本写进实测报告。插件版本必须与 OpenSearch 版本完全一致。
ARG OPENSEARCH_VERSION=2.19.1
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}

# 官方中文分词插件（与 OpenSearch 同版本发布）
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-smartcn

# 社区 IK 插件（可选）：需要与 OpenSearch 版本严格匹配的发行包。
# 找到对应版本的 zip 地址后取消注释，例如：
# ARG IK_URL=
# RUN /usr/share/opensearch/bin/opensearch-plugin install --batch ${IK_URL}
