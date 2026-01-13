import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Any

# =============================================================================
# CONFIGURAÇÃO DE DIRETÓRIOS E ARQUIVOS DE LOG
# =============================================================================
LOG_DIR = Path(__file__).resolve().parents[2] / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# CCXT_LOG_FILE = LOG_DIR / "ccxt.log"  # Logs do ccxt (biblioteca externa)

# =============================================================================
# CONFIGURAÇÃO DE MÓDULOS
# Format: "module_name":  {"level": "LEVEL", "color": "console_color"}
#
# Níveis:  DEBUG, INFO, WARNING, ERROR, CRITICAL
# Cores: green, cyan, magenta, yellow, red, blue, white
# Modificadores: bold, italic, dim, bright_
# =============================================================================
MODULES = {
    "ccxt_decorator": {"level": "INFO", "color": "bright_yellow"},
    "settings": {"level": "INFO", "color": "bright_magenta"},
    "exchange_conn": {"level": "DEBUG", "color": "bright_magenta"},
    "manage_orders": {"level": "DEBUG", "color": "bright_green"},
}

# =============================================================================
# CONFIGURAÇÃO BASE DO LOGGING
# =============================================================================
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "file": {"format": "%(asctime)s|%(name)s|%(levelname)s|%(message)s"}
    },
    "handlers": {},  # Será preenchido dinamicamente no loop abaixo
    "loggers": {},
}

# =============================================================================
# CONFIGURAÇÃO AUTOMÁTICA DOS MÓDULOS
# =============================================================================
for module, props in MODULES.items():
    color = props["color"]
    level = props["level"]

    # Arquivo de log específico para o módulo
    module_log_file = LOG_DIR / f"{module}.log"

    # Formatter console com cor específica
    LOGGING_CONFIG["formatters"][f"console_{module}"] = {
        "format": f"[{color}][{module.upper()}][/{color}] %(message)s"
    }

    # Handler de arquivo específico para o módulo
    LOGGING_CONFIG["handlers"][f"file_{module}"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "file",
        "filename": str(module_log_file),
        "maxBytes": 5 * 1024 * 1024,  # 5MB
        "backupCount": 5,
        "encoding": "utf-8",
    }

    # Handler de console específico
    LOGGING_CONFIG["handlers"][f"console_{module}"] = {
        "()": "rich.logging.RichHandler",
        "formatter": f"console_{module}",
        "rich_tracebacks": False,
        "tracebacks_show_locals": False,
        "show_time": True,
        "show_level": True,
        "omit_repeated_times": False,
        "enable_link_path": False,
        "show_path": False,
        "markup": True,
    }

    # Logger do módulo usa:  console próprio + arquivo próprio
    LOGGING_CONFIG["loggers"][f"bot.{module}"] = {
        "handlers": [f"console_{module}", f"file_{module}"],
        "level": level,
        "propagate": False,
    }

# =============================================================================
# CONFIGURAÇÃO DE BIBLIOTECAS EXTERNAS
# =============================================================================
# LOGGING_CONFIG["loggers"]["ccxt"] = {
#     "handlers": ["file_ccxt"],
#     "level": "DEBUG",
#     "propagate": False,
# }

# =============================================================================
# APLICAR CONFIGURAÇÃO
# =============================================================================
dictConfig(LOGGING_CONFIG)


# =============================================================================
# FUNÇÃO AUXILIAR
# =============================================================================
def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger já configurado pelo dictConfig do logger.py

    Args:
        name: Nome completo do logger (ex: "bot. settings")

    Returns:
        Logger configurado
    """
    return logging.getLogger(name)
