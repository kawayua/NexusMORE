"""Check a Chinese Markdown review draft without approving or exporting it."""
import argparse
import json
from pathlib import Path
from modelcrew.modeling_paper import validate_draft

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('markdown', type=Path)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--reviews', type=Path, help='Check separate file-level review scopes without creating approvals')
    args = parser.parse_args()
    report = validate_draft(args.markdown, args.catalog)
    if args.reviews:
        from modelcrew.writing_reviews import review_status
        review=json.loads(args.reviews.read_text(encoding='utf-8'))
        if review.get('review_version')!='2.0.0':raise ValueError('Use a separate-review 2.0.0 bundle')
        report['separate_reviews']=review_status(args.markdown,args.catalog,review.get('manuscript_review'),review.get('figure_selection_review'))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['status'] == 'passed' else 1)
