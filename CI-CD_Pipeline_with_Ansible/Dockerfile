# Dockerfile - CI/CD Pipeline with Ansible: offline CI image
#
# This lab's GitLab CI jobs (build_and_stage, deploy_production) run on a
# training VM with no internet access, on purpose - that's how this
# course's lab environment is provisioned. Neither Docker Hub nor PyPI is
# reachable from inside a CI job here, so pulling `python:3.11-slim` fresh
# and then `pip install`-ing ansible-core at job runtime (the obvious,
# "normal" way to write this) simply cannot work.
#
# This image exists to solve that: it bakes ansible-core (and procps, for
# run_playbook.sh's own `pkill` cleanup of any leftover mock device fleet)
# directly into the image itself, ONE TIME, on a machine that DOES have
# internet access - so the CI job never needs to reach out to anything at
# runtime. .gitlab-ci.yml references this image by name/tag; the GitLab
# Runner on the offline VM only ever needs to find it already sitting in
# its local Docker image cache.
#
# No collection beyond ansible-core is needed - every RESTCONF call in
# this course's playbook goes through ansible.builtin.uri (ships with
# ansible-core), never ansible.netcommon.restconf_config, on purpose - see
# site.yml's TODO 08 for why. There is nothing else to vendor offline.
#
# ---------------------------------------------------------------------------
# One-time build (on a machine WITH internet access):
#
#     docker build -t cicd-lab-ansible:latest -f Dockerfile .
#
# Save it to a single portable file:
#
#     docker save -o cicd-lab-ansible-latest.tar cicd-lab-ansible:latest
#
# Move that .tar file to the offline GitLab Runner host however you can
# (USB drive, scp over the local network, shared folder - anything that
# doesn't require the offline host itself to reach the internet).
#
# On the offline host, load it into the same Docker daemon the runner
# uses:
#
#     docker load -i cicd-lab-ansible-latest.tar
#
# Confirm it's there:
#
#     docker images | grep cicd-lab-ansible
#
# See README.md -> "Offline CI environment" for the matching runner
# config.toml setting (pull_policy) that stops the runner from ever
# trying to re-pull this image over the network.
# ---------------------------------------------------------------------------

FROM python:3.11-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ansible-core
