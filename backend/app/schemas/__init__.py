from __future__ import annotations

from backend.app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from backend.app.schemas.citation import (
    CitationListResponse,
    CitationResponse,
    ReferenceIssueListResponse,
    ReferenceIssueResponse,
)
from backend.app.schemas.claim import (
    ClaimCitationItem,
    ClaimDetailResponse,
    ClaimFilterParams,
    ClaimListResponse,
    ClaimResponse,
)
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentQueryParams,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    PaginationMeta,
)
from backend.app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse
from backend.app.schemas.report import GenerateReportRequest, ReportResponse
from backend.app.schemas.review import ReviewCreateRequest, ReviewHistoryResponse
from backend.app.schemas.source import (
    EvidencePassageResponse,
    ResearchSourceResponse,
    SourceVersionResponse,
)
from backend.app.schemas.user import (
    AdminRoleUpdate,
    AdminStatusUpdate,
    UserBase,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from backend.app.schemas.verification import (
    DocumentVerificationSummary,
    ProcessingJobResponse,
    VerificationEvidenceItem,
    VerificationResultResponse,
)

__all__ = [
    "AdminRoleUpdate",
    "AdminStatusUpdate",
    "ChangePasswordRequest",
    "CitationListResponse",
    "CitationResponse",
    "ClaimCitationItem",
    "ClaimDetailResponse",
    "ClaimFilterParams",
    "ClaimListResponse",
    "ClaimResponse",
    "DocumentListResponse",
    "DocumentQueryParams",
    "DocumentResponse",
    "DocumentStatusResponse",
    "DocumentUploadResponse",
    "DocumentVerificationSummary",
    "EvidencePassageResponse",
    "FeedbackCreateRequest",
    "FeedbackResponse",
    "GenerateReportRequest",
    "LoginRequest",
    "MessageResponse",
    "PaginationMeta",
    "ProcessingJobResponse",
    "RefreshTokenRequest",
    "ReferenceIssueListResponse",
    "ReferenceIssueResponse",
    "RegisterRequest",
    "ReportResponse",
    "ResearchSourceResponse",
    "ReviewCreateRequest",
    "ReviewHistoryResponse",
    "SourceVersionResponse",
    "TokenResponse",
    "UserBase",
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "VerificationEvidenceItem",
    "VerificationResultResponse",
]
