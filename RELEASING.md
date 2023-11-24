1. Create a new virtual environment following the instructions in `README.md`.
   Make sure to also install all dependencies for the documentation.

2. Make certain your branch is in sync with head:

       git pull upstream main

3. Do a clean doc build:

       hatch run doc:clean
       hatch run doc:build
       hatch run doc:serve

   Navigate to http://localhost:8000 and ensure it looks OK (particularly
   do a visual scan of the gallery thumbnails).

4. Update version in `altair_tiles/__init__.py`:

5. Commit change and push to main:

       git add . -u
       git commit -m "MAINT: bump version to 5.0.0"
       git push upstream main

6. Tag the release:

       git tag -a v5.0.0 -m "version 5.0.0 release"
       git push upstream v5.0.0

7. Build source & wheel distributions:

       hatch clean  # clean old builds & distributions
       hatch build  # create a source distribution and universal wheel

8. Publish to PyPI (Requires correct PyPI owner permissions):

        hatch publish

9. Build and publish docs:

        hatch run doc:build-and-publish

10. Update version to e.g. 5.1.0dev in `altair_tiles/__init__.py`:

11. Commit change and push to main:

        git add . -u
        git commit -m "MAINT: bump version to 5.1.0dev"
        git push upstream main

12. Add release in https://github.com/binste/dbt-ibis/releases and select the version tag
