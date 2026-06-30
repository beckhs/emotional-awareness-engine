# Contributing to Emotional Awareness Engine

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/emotional-awareness-engine.git`
3. Create a branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Run the tests: `python3 -m pytest test_engine.py -v`
6. Submit a pull request

## Development Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/emotional-awareness-engine.git
cd emotional-awareness-engine

# Run tests (no dependencies needed — uses standard library only)
python3 -m unittest test_engine.py -v

# Run the basic analysis engine
python3 outreach_engine_basic.py
```

## What We're Looking For

- **New mood keywords** for different languages or dialects
- **Improved pattern detection** algorithms
- **Bug fixes** and edge case handling
- **Documentation** improvements
- **Tests** for uncovered scenarios

## Code Guidelines

- Keep it dependency-free (standard library only for the core engine)
- Add tests for any new functionality
- Use English for code comments and docstrings
- Follow PEP 8 style
- Keep functions focused and well-documented

## What NOT to Submit

The following features are part of the **premium version** and won't be accepted into the open-source repo:

- Proactive message generation
- Message delivery (Telegram/Discord integration)
- Self-improving pipeline logic
- Rate limiting policies
- Multi-channel support

If you want access to these features, see the [premium version](https://gumroad.com/l/emotional-awareness-engine).

## Reporting Issues

Please use GitHub Issues to report bugs. Include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
