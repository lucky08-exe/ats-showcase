# Combined, deduplicated, and organized for maintenance
TECH_TERMS = {
    # --- Carbon Robotics / AI / Robotics Specific ---
    "PyTorch",
    "pytorch lightning",
    "C++",
    "computer vision",
    "vision transformers",
    "anchor-free detectors",
    "embeddings",
    "web services",
    "ADAS",
    "sensor fusion",
    "perception pipelines",
    "real-time inference",
    "Large Plant Model",
    "LPM",
    # --- Languages ---
    "python",
    "java",
    "javascript",
    "typescript",
    "rust",
    "go",
    "golang",
    "c#",
    # --- Frameworks & Libraries ---
    "react",
    "angular",
    "vue",
    "django",
    "flask",
    "spring",
    "spring boot",  # #513: compound, so "Spring Boot" does not yield bare "spring"
    "tensorflow",
    "sklearn",
    "grpc",
    # --- Cloud & Infrastructure ---
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "docker",
    "kafka",
    "terraform",
    # --- Databases & Search ---
    "postgresql",
    "mongodb",
    "redis",
    "elasticsearch",
    "lightning",
    # --- Tools & Collaboration ---
    "git",
    "github",
    "gitlab",
    "jira",
}

# Words that, directly after "<ambiguous term>-", count as tech evidence ("Go-based services").
# Any other hyphen after an ambiguous term reads as an English compound ("Go-to-market", "Go-live").
# Membership is a judgment call pending real JD examples; do not widen without evidence (#513, #553).
HYPHEN_TECH_SUFFIXES = frozenset({"based", "native", "lang", "like"})
