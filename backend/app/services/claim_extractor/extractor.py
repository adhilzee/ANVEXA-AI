from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.models.enums import ClaimType

NUMERICAL_REGEX = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\d+\.\d+|\b\d{2,}\b|p\s*[<=]\s*0?\.\d+|CI\b|\b\d+\s*(?:mg|ml|kg|km|meters|hours|days|years|samples|participants)\b)",
    re.IGNORECASE,
)

STATISTICAL_REGEX = re.compile(
    r"\b(?:statistically\s+significant|p-value|confidence\s+interval|standard\s+deviation|mean\s*[=±]|median|t-test|anova|chi-square|correlation|regression\s+coefficient|odds\s+ratio|hazard\s+ratio|r\s*=\s*0?\.\d+)\b",
    re.IGNORECASE,
)

COMPARATIVE_REGEX = re.compile(
    r"\b(?:outperformed|higher\s+than|lower\s+than|greater\s+than|less\s+than|superior\s+to|inferior\s+to|doubled|tripled|reduced\s+by|increased\s+by|decreased\s+by|more\s+effective|faster\s+than|state-of-the-art)\b",
    re.IGNORECASE,
)

CAUSAL_REGEX = re.compile(
    r"\b(?:causes?|caused|causing|leads?\s+to|led\s+to|results?\s+in|resulted\s+in|induces?|induced|triggers?|triggered|contributes?\s+to|produces?|prevented|prevents?)\b",
    re.IGNORECASE,
)

TEMPORAL_REGEX = re.compile(
    r"\b(?:between\s+\d{4}\s+and\s+\d{4}|from\s+\d{4}\s+to\s+\d{4}|during\s+the\s+period|over\s+a\s+\d+[- ](?:year|month|day)\s+period|in\s+(?:19\d{2}|20\d{2})|since\s+\d{4})\b",
    re.IGNORECASE,
)

SKIP_PATTERNS = [
    re.compile(r"^table\s+\d+", re.IGNORECASE),
    re.compile(r"^figure\s+\d+", re.IGNORECASE),
    re.compile(r"^fig\.\s*\d+", re.IGNORECASE),
    re.compile(r"the\s+rest\s+of\s+this\s+paper\s+is\s+organized", re.IGNORECASE),
    re.compile(r"section\s+\d+\s+describes", re.IGNORECASE),
    re.compile(r"in\s+section\s+\d+", re.IGNORECASE),
]


@dataclass
class ExtractedClaim:
    original_text: str
    normalized_text: str
    context_text: str
    claim_type: ClaimType
    requires_external_verification: bool
    page_number: int
    paragraph_number: int
    extraction_method: str = "rule_based_nlp"


def dehyphenate_text(text: str) -> str:
    """Fix mid-word line-break hyphenation where line wraps split words across lines with a hyphen and whitespace.

    - Compound prefixes (e.g. 'pre- trained' -> 'pre-trained', 'state- of- the- art' -> 'state-of-the-art')
      are normalized preserving their hyphen.
    - Broken word wrap hyphens (e.g. 'down- stream' -> 'downstream', 'knowl- edge' -> 'knowledge')
      are rejoined cleanly.
    """
    if not text:
        return ""
    # 1. Normalize line-broken compound words with hyphen preserved
    compound_words = (
        r"\b(pre|non|self|cross|fine|multi|state|semi|zero|few|task|domain|end|real|open|meta|"
        r"well|high|low|wide|large|in|out|all|short|long|sequence|token|of|to|the)-\s+([a-zA-Z]+)"
    )
    for _ in range(3):
        text = re.sub(compound_words, r"\1-\2", text, flags=re.IGNORECASE)
    # 2. General line-break hyphenation where words were broken across lines (e.g. down- stream -> downstream)
    return re.sub(r"([a-zA-Z])-\s+([a-zA-Z])", r"\1\2", text)


def strip_abstract_front_matter(text: str) -> str:
    """Detect if the opening text block contains an 'Abstract' heading/marker (within first ~1,500 characters)
    and strip everything up to and including 'Abstract' (along with any trailing colon, dashes, or whitespace)
    so claim extraction begins cleanly at the opening sentence of the abstract."""
    if not text:
        return ""
    prefix_window = text[:1500]
    match = re.search(r"(?i)\babstract\b\s*[:\-\u2013\u2014]?\s*", prefix_window)
    if match:
        return text[match.end():].lstrip()
    return text


def strip_section_heading(text: str) -> str:
    """Strip leading section numbers and titles from extracted sentences.

    e.g. '2.5 Decoding At test time...' -> 'At test time...'
         '3.1 Open-domain Question Answering Open-domain question answering...' -> 'Open-domain question answering...'
         '1 Introduction Pre-trained neural...' -> 'Pre-trained neural...'
         'General-Purpose Architectures for NLP Much previous work...' -> 'Much previous work...'
         'Learned Retrieval Pre-trained neural...' -> 'Pre-trained neural...'
         'Memory-based Architectures In contrast to...' -> 'In contrast to...'
    """
    if not text:
        return ""
    s = text.replace("ﬁ", "fi").replace("ﬂ", "fl")

    # 1. Strip repeated section phrases e.g. "3.1 Open-domain Question Answering Open-domain..."
    m_rep = re.match(
        r"^\s*(?:(?:Section\s+)?(?:\d+(?:\.\d+)*|[IVXLCDM]+\.?|[A-Z]\.))\s+([A-Za-z0-9\-–—/:\'\"]{3,50}?)\s+\1\b",
        s,
        re.IGNORECASE,
    )
    if m_rep:
        return s[m_rep.start(1) + len(m_rep.group(1)):].strip()

    # 2. Match section number + title ending before sentence starters
    sentence_starters = (
        r"(?:Pre-trained|Large|At\s|As\s|We\s|Our\s|The\s|To\s|In\s|Prior\s|Table\s|Figure\s|FEVER\b|RAG\b|Section\s)"
    )
    m_start = re.match(
        r"^\s*(?:(?:Section\s+)?(?:\d+(?:\.\d+)*|[IVXLCDM]+\.?|[A-Z]\.))\s+(?:[A-Za-z0-9\-–—/:]+\s+){1,7}?(?="
        + sentence_starters
        + ")",
        s,
    )
    if m_start:
        return s[m_start.end():].strip()

    # 3. Fallback: Section num + single/double title word e.g. "2.5 Decoding At..." or "2.4 Training We..."
    m_simple = re.match(
        r"^\s*(?:(?:Section\s+)?(?:\d+(?:\.\d+)*|[IVXLCDM]+\.?|[A-Z]\.))\s+([A-Z][a-zA-Z0-9\-–—/:]*(?:\s+[A-Z][a-zA-Z0-9\-–—/:]*){0,3})\s+([A-Z].*)$",
        s,
    )
    if m_simple:
        return m_simple.group(2).strip()

    # 4. Strip unnumbered Title-Case subheadings followed immediately by a sentence
    # e.g. "General-Purpose Architectures for NLP Much previous work..." -> "Much previous work..."
    #      "Learned Retrieval Pre-trained neural..." -> "Pre-trained neural..."
    #      "Memory-based Architectures In contrast to..." -> "In contrast to..."
    title_word = r"(?:[A-Z][a-zA-Z0-9\-]*(?:-[A-Za-z0-9]+)*|[A-Z]{2,6}|for|and|in|of|the|to|with|on|at|by|from|a|an|or)"
    sentence_starters_no_prefix = (
        r"(?:Much|Many|Most|Pre-trained|Large|In\s|We\s|Our\s|The\s|This\s|These\s|Recent|While|Although|However|Prior|To\s|For\s|As\s|At\s|Following|Unlike|Instead|Here|First|Second|Third|Finally)\b"
    )
    heading_academic_nouns = (
        r"(?:Architectures?|Retrieval|Models?|Methods?|Approaches?|Systems?|Decoding|Training|"
        r"Experiments?|Evaluation|Setup|Analysis|Tasks?|Generation|NLP|QA|Frameworks?|Datasets?|"
        r"Overview|Background|Results?|Memory|Representations?|Answering|Mechanisms?|[A-Z]{2,6})"
    )
    m_unnum = re.match(
        rf"^\s*(?:{title_word}\s+){{0,5}}{heading_academic_nouns}\s+(?={sentence_starters_no_prefix}|[A-Z][a-zA-Z\-]*\s+[a-z]{{2,}})",
        s,
    )
    if m_unnum:
        return s[m_unnum.end():].strip()

    m_unnum2 = re.match(
        rf"^\s*(?:[A-Z][a-zA-Z0-9\-]*(?:-[A-Za-z0-9]+)*\s+){{1,4}}[A-Z][a-zA-Z0-9\-]*(?:-[A-Za-z0-9]+)*\s+(?={sentence_starters_no_prefix})",
        s,
    )
    if m_unnum2:
        return s[m_unnum2.end():].strip()

    return s


def is_speculative_future_work(sentence: str) -> bool:
    """Detect speculative or future-work sentences that describe hypothetical future research
    or tentative possibilities rather than verified empirical claims.
    (e.g., 'may work well', 'promising future work', 'leave ... for future work').
    """
    if not sentence:
        return False
    future_work_patterns = [
        re.compile(r"\b(?:leave|leaves|left|leaving)\b.*?\b(?:for|as)\s+future\s+(?:work|research)\b", re.IGNORECASE),
        re.compile(r"\bpromising\s+(?:avenue|direction|area|topic|extension)?\s*(?:for\s+)?future\s+(?:work|research)\b", re.IGNORECASE),
        re.compile(r"\b(?:(?:for|in|as|subject\s+of|deferred\s+to|reserved\s+for)\s+future\s+(?:work|research)|future\s+(?:work|research)\s+(?:will|should|could|might|may|is\s+needed))\b", re.IGNORECASE),
        re.compile(r"\b(?:may|might|could)\s+(?:also\s+)?(?:work\s+well|perform\s+well|be\s+promising|be\s+explored|be\s+extended|be\s+applicable)\b", re.IGNORECASE),
        re.compile(r"\b(?:we\s+(?:speculate|conjecture|hypothesize)|remains\s+(?:to\s+be\s+seen|an\s+open\s+question|unclear)|it\s+is\s+conceivable\s+that)\b", re.IGNORECASE),
    ]
    return any(p.search(sentence) for p in future_work_patterns)


def is_first_person_setup(sentence: str) -> bool:
    """Detect pure first-person experimental setup sentences describing internal paper parameters
    (e.g., 'We consider k...', 'We use the document encoder...', 'Following X, we use...').
    """
    if not sentence:
        return False
    # If the sentence makes an empirical comparative assertion, it is not a pure setup sentence
    if re.search(r"\b(?:outperformed?|superior\s+to|higher\s+than|lower\s+than|state-of-the-art)\b", sentence, re.IGNORECASE):
        return False

    setup_pattern = re.compile(
        r"^\s*(?:(?:following\s+[^,]+|for\s+(?:all\s+models|our\s+experiments?|setup|training|decoding)|"
        r"in\s+(?:our\s+)?(?:experiments?|setup|work|implementation|architecture)),\s*)?"
        r"(?:we|our\s+setup|our\s+implementation)\s+(?:also\s+)?"
        r"(?:use|uses|used|consider|considers|considered|set|sets|adopt|adopts|adopted|"
        r"choose|chooses|chose|initialize|initializes|initialized|train|trains|trained|"
        r"fine-tune|fine-tunes|fine-tuned|implement|implements|implemented|apply|applies|applied|"
        r"select|selects|selected|fix|fixes|fixed|run|runs|ran|define|defines|defined|"
        r"employ|employs|employed|tune|tunes|tuned|parametrize|parametrized)\b",
        re.IGNORECASE,
    )
    return bool(setup_pattern.search(sentence))


def split_sentences(text: str) -> list[str]:
    """Split text into sentences while respecting common academic abbreviations (e.g., et al., i.e., e.g., fig.)."""
    cleaned = text.replace("et al.", "et_al_dot").replace("i.e.", "i_e_dot").replace("e.g.", "e_g_dot").replace("Fig.", "Fig_dot")
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    results = []
    for s in raw_sentences:
        restored = s.replace("et_al_dot", "et al.").replace("i_e_dot", "i.e.").replace("e_g_dot", "e.g.").replace("Fig_dot", "Fig.")
        restored = restored.strip()
        if len(restored) > 15:
            results.append(restored)
    return results


def classify_claim_type(sentence: str) -> tuple[ClaimType, bool]:
    """Determine the primary ClaimType and whether external verification is required."""
    # Speculative or future-work sentences are excluded from empirical claim verification
    if is_speculative_future_work(sentence):
        return ClaimType.OTHER, False

    # Pure first-person experimental setup sentences are author design choices excluded from external verification
    if is_first_person_setup(sentence):
        return ClaimType.DESCRIPTIVE, False

    is_statistical = bool(STATISTICAL_REGEX.search(sentence))
    is_numerical = bool(NUMERICAL_REGEX.search(sentence))
    is_comparative = bool(COMPARATIVE_REGEX.search(sentence))
    is_causal = bool(CAUSAL_REGEX.search(sentence))
    is_temporal = bool(TEMPORAL_REGEX.search(sentence))

    if is_statistical:
        return ClaimType.STATISTICAL, True
    if is_temporal:
        return ClaimType.TEMPORAL, True
    if is_numerical:
        return ClaimType.NUMERICAL, True
    if is_comparative:
        return ClaimType.COMPARATIVE, True
    if is_causal:
        return ClaimType.CAUSAL, True

    # Check if sentence makes empirical assertion or cites work
    has_citation = bool(re.search(r"\[\d+\]|\([A-Za-z]+.*,\s*\d{4}\)", sentence))
    if has_citation:
        return ClaimType.DESCRIPTIVE, True

    # Check for general descriptive assertion verbs
    descriptive_keywords = [
        "demonstrate", "show", "found that", "observed", "conclude", "indicated",
        "consist", "propose", "present", "describe", "architecture", "design", "evaluate", "achieve", "require"
    ]
    if any(term in sentence.lower() for term in descriptive_keywords):
        return ClaimType.DESCRIPTIVE, True

    return ClaimType.OTHER, False


REFERENCES_HEADING_REGEX = re.compile(
    r"^(?:(?:Section\s+)?(?:\d+(?:\.\d+)*|[IVXLCDM]+\.?|[A-Z]\.)\s+)?(?:References|Bibliography|Works\s+Cited)\b\s*$",
    re.IGNORECASE,
)


def is_references_heading(text: str) -> bool:
    """Detect if text represents a standalone References or Bibliography section heading."""
    if not text:
        return False
    stripped = text.strip()
    return bool(REFERENCES_HEADING_REGEX.match(stripped))


def truncate_at_references(text: str) -> tuple[str, bool]:
    """If text contains a References/Bibliography heading, truncate text before it and return (clean_text, True)."""
    if not text:
        return "", False
    pattern = re.compile(
        r"(?:^|\n)\s*(?:(?:Section\s+)?(?:\d+(?:\.\d+)*|[IVXLCDM]+\.?|[A-Z]\.)\s+)?(?:References|Bibliography|Works\s+Cited)\b\s*(?:\n|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return text[:match.start()].strip(), True
    return text, False


def is_valid_claim_candidate(sentence: str) -> bool:
    """Filter out non-claim boilerplate sentences, citation entries, tabular rows, and speculative future-work."""
    if not sentence or len(sentence) < 25 or len(sentence) > 600:
        return False
    if is_speculative_future_work(sentence):
        return False
    if is_references_heading(sentence):
        return False

    # 1. Filter out sentences starting with bracketed reference numbers e.g. '[66] Thomas Wolf et al...'
    if re.match(r"^\s*\[\d+\]", sentence):
        return False

    # 2. Filter out standalone doi:, URL, ArXiv, and bibliography citation lines
    if re.match(r"^\s*(?:doi:\s*|https?://|url\s*:?\s*https?://|arxiv\b|abs/\d+\.\d+)", sentence, re.IGNORECASE):
        return False
    if re.search(r"\b(?:arxiv,\s*abs/\d+\.\d+|doi:\s*10\.\d{4,9}/[^\s]+|url\s+https?://)", sentence, re.IGNORECASE) and not re.search(r"\b(?:we|our|demonstrate|show|achieved?|outperformed?|results?|found)\b", sentence, re.IGNORECASE):
        return False

    # 3. Filter out dense tabular/numeric lines (>35% digits/numbers e.g. 'Natural Questions 79169 8758 3611...')
    digit_count = sum(1 for ch in sentence if ch.isdigit())
    if (digit_count / len(sentence)) > 0.35:
        return False
    words = sentence.split()
    if len(words) >= 4:
        numeric_words = sum(1 for w in words if re.match(r"^[\d,.\-%±/]+$", w))
        if (numeric_words / len(words)) > 0.35:
            return False

    for pat in SKIP_PATTERNS:
        if pat.search(sentence):
            return False
    return True


def extract_claims_from_paragraph(
    paragraph: str,
    page_number: int,
    paragraph_number: int,
) -> list[ExtractedClaim]:
    """Extract and classify candidate claims from a single paragraph."""
    # Check for references section heading and truncate any bibliography text
    clean_paragraph, _ = truncate_at_references(paragraph)
    if not clean_paragraph:
        return []
    paragraph = clean_paragraph

    # De-hyphenate line-break words
    paragraph = dehyphenate_text(paragraph)

    # For opening front-matter blocks, strip title/authors/affiliations before 'Abstract'
    if (page_number == 1 and paragraph_number == 1) or ("abstract" in paragraph[:1500].lower()):
        paragraph = strip_abstract_front_matter(paragraph)

    sentences = split_sentences(paragraph)
    claims: list[ExtractedClaim] = []

    for idx, sentence in enumerate(sentences):
        # Strip leading section number headings (e.g., '2.5 Decoding ', '3.1 Open-domain Question Answering ')
        sentence = strip_section_heading(sentence)
        if not is_valid_claim_candidate(sentence):
            continue

        claim_type, requires_verif = classify_claim_type(sentence)

        # Build context from previous and next sentences
        context_parts = []
        if idx > 0:
            context_parts.append(sentences[idx - 1])
        context_parts.append(sentence)
        if idx < len(sentences) - 1:
            context_parts.append(sentences[idx + 1])
        context = " ".join(context_parts)

        # Normalize text
        normalized = " ".join(sentence.split())

        # Include claims that require verification or have substantial claim types
        if requires_verif or claim_type != ClaimType.OTHER:
            claims.append(
                ExtractedClaim(
                    original_text=sentence,
                    normalized_text=normalized,
                    context_text=context,
                    claim_type=claim_type,
                    requires_external_verification=requires_verif,
                    page_number=page_number,
                    paragraph_number=paragraph_number,
                    extraction_method="rule_based_academic_extractor",
                )
            )

    return claims
