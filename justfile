set shell := ["bash", "-lc"]

default:
    @just --list

setup:
    uv sync --group dev
    uv run maturin develop

fmt:
    cargo fmt --all
    uv run ruff format src/fly_stick tests examples

check:
    cargo fmt --all -- --check
    cargo clippy --all-targets --all-features
    uv run ruff check src/fly_stick tests examples
    uv run ruff format src/fly_stick tests examples --check
    uv run mypy src/fly_stick tests

test-rust:
    cargo test --all-features

test-python:
    uv run maturin develop
    uv run pytest tests

test: test-rust test-python

build:
    uv run maturin build --release

pre-commit: check test build
