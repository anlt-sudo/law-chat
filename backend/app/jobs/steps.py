"""Tên bước pipeline dùng chung (F15 §6 – cột pipeline_job.step)."""

CRAWL = "crawl"
NORMALIZE = "normalize"
PARSE = "parse"
RELINK = "relink"
EXTRACT = "extract"
CONSOLIDATE = "consolidate"
INDEX = "index"
EVALUATE = "evaluate"

NOOP = "noop"  # bước kiểm thử hạ tầng hàng đợi
