from langchain_groq import ChatGroq

from config.settings import rate_limiter


llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.5,
    rate_limiter=rate_limiter,
)
