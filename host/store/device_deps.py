"""Pinned predecessors unchanged; Android lifecycle is an isolated schema/version."""
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'runtime-dependencies'
sys.path.insert(0,str(BASE/'p3-4-knowledge-publication'))
from p34deps import records,compiler,canonical,digest,verify_predecessor
import flow_store_v2 as flow_store
