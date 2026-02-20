
import logging
import argparse

# Configuração Padrão
LOG_LEVEL_MAP = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
    5: logging.NOTSET  # Ver tudo
}

def setup_logger():
    parser = argparse.ArgumentParser(description="3D Printer Connection Hub")
    parser.add_argument('--log-level', type=int, choices=range(0, 6), default=3, 
                        help="Nível de Log: 0=Critical, 1=Error, 2=Warning, 3=Info(Default), 4=Debug, 5=Trace(All)")
    
    # Parse just known args to avoid conflict with Flask reloader if any
    args, _ = parser.parse_known_args()
    
    level = LOG_LEVEL_MAP.get(args.log_level, logging.INFO)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Supress Flask/Werkzeug logs if level is below INFO (3)
    if args.log_level < 3:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    logger = logging.getLogger("Hub")
    return logger

logger = setup_logger()
# Expor logging padrão para facilitar substituição de print
def log_info(msg): logger.info(msg)
def log_error(msg): logger.error(msg)
def log_warn(msg): logger.warning(msg)
def log_debug(msg): logger.debug(msg)
