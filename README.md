# Patchew Documentation

## About

Patchew, pronounced as /pæ'tʃu:/, is a system built to automatically _chew_
patches that are submitted as emails on mailing lists.

## What can it do, exactly?

It can:

 - Collect and index the patch series.
 - Apply the patch series on top of git master, and push to a git remote.
 - Trigger customizable tests when a series appears.
 - Support multiple testers with that run in different environments.
 - Send email notification when a test fails.
 - Recognize various statuses (picking up "Reviewed-by", "Tested-by", etc.) of
   the patch series from the patch email and replies.
 - Search or apply series from the command line.
 - Deploy your server to [openshift](https://openshift.redhat.com) instantly.
 - Manage multiple projects with separate configurations.

## Submit a feature request or a bug report

[https://github.com/patchew-project/patchew/issues/new](https://github.com/patchew-project/patchew/issues/new)

## Known issues

 - Binary patches are not recognized correctly.

## License

See LICENSE file.
