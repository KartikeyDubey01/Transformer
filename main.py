import argparse
import sys
import json
import logging
from pathlib import Path

from src.sources.csv_source import CSVSource
from src.sources.json_source import ATSJsonSource
from src.sources.text_source import RecruiterNotesSource
from src.merger.merger import CandidateMerger
from src.projector.projector import OutputProjector
from src.projector.validator import SchemaValidator

SOURCE_REGISTRY = {
    ".csv": CSVSource,
    ".json": ATSJsonSource,
    ".txt": RecruiterNotesSource
}

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("files", nargs="+", help="Input files (.csv, .json, .txt)")
    parser.add_argument("--config", help="Path to projection config JSON")
    parser.add_argument("--output", help="Path to output JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    all_cirs = []
    
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File not found, skipping: {file_path}")
            continue
            
        ext = path.suffix.lower()
        if ext not in SOURCE_REGISTRY:
            logger.warning(f"Unknown extension {ext}, skipping: {file_path}")
            continue
            
        source_class = SOURCE_REGISTRY[ext]
        source_instance = source_class(file_path)
        
        cirs = source_instance.extract()
        logger.info(f"Extracted {len(cirs)} record(s) from {path.name}")
        all_cirs.extend(cirs)
        
    if not all_cirs:
        logger.error("No valid records extracted from any source.")
        sys.exit(1)
        
    merger = CandidateMerger()
    merged_profiles = merger.process(all_cirs)
    logger.info(f"Merged into {len(merged_profiles)} unique candidate profile(s)")
    
    # Load config
    config = None
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config {args.config}: {e}")
            sys.exit(1)
            
    projector = OutputProjector(config)
    validator = SchemaValidator(projector.config)
    
    final_output = []
    
    for profile in merged_profiles:
        projected = projector.project(profile)
        issues = validator.validate(projected)
        for issue in issues:
            logger.warning(f"Validation issue for {projected.get('candidate_id', 'unknown')}: {issue}")
        final_output.append(projected)
        
    # Output
    out_json = json.dumps(final_output, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(out_json)
            logger.info(f"Output written to {args.output}")
        except Exception as e:
            logger.error(f"Failed to write output to {args.output}: {e}")
            sys.exit(1)
    else:
        print(out_json)

if __name__ == "__main__":
    main()
