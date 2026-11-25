# Offline news relevance lab

This public test repository contains only generic, synthetic fixtures. No production configuration, watchlists, CRM identifiers, article archives or private code are included.

Run the tested generic proximity helper with Python 3.11+:

```sh
cd news_lab
python -m unittest -v test_body_evidence
```

The helper checks nearby text around an already matched entity. It does not establish identity or authorize publication. The production integration, publication checks, and separately labelled holdout data are maintained outside this public repository.
