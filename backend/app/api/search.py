"""检索接口（docs/api.md §7.1）。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, SettingsDep, TextIndexDep
from app.modules.documents import service as documents_service
from app.modules.search import SearchRequestData, params_from_settings, search
from app.modules.search.schemas import (
    ChannelStatusOut,
    SearchHitOut,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/api", tags=["search"])


# 普通 def：数据库和 OpenSearch 的调用都是阻塞的，FastAPI 会放到线程池里执行
@router.post("/search", response_model=SearchResponse)
def search_documents(
    body: SearchRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    text_index: TextIndexDep,
) -> SearchResponse:
    switches = body.channels.model_dump() if body.channels else {}
    outcome = search(
        session,
        user,
        SearchRequestData(
            query=body.query,
            top_k=body.top_k,
            channels=switches,
            source_types=body.source_types,
        ),
        client=text_index,
        params=params_from_settings(settings),
    )

    ordered = [outcome.documents[hit.document_id] for hit in outcome.hits]
    documents = documents_service.to_document_out(session, user, ordered)
    return SearchResponse(
        hits=[
            SearchHitOut(
                document=document,
                score=hit.score,
                channels=hit.channels,
                evidence=hit.evidence,
            )
            for hit, document in zip(outcome.hits, documents, strict=True)
        ],
        channels=[
            ChannelStatusOut(
                channel=report.channel,
                status=report.status,
                took_ms=report.took_ms,
                detail=report.detail,
            )
            for report in outcome.channels
        ],
        took_ms=outcome.took_ms,
    )
