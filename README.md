# ArchivesSpace API wrapper

Wrapper for working with the ArchivesSpace API that provides convenience functions for the Bentley Historical Library's use of the application.

## Installation

`pip install git+https://github.com/bentley-historical-library/bhlaspaceapiclient.git`

## Use

```python
from bhlaspaceclient import ASpaceClient
aspace = ASpaceClient()
aspace.get_archival_object(1234)
```