## Python Test Guide

When writing tests for python code:

1. Always use pytest for tests in python code
2. Assume an appropriate test file already exists, find it, and suggest tests get appended to that file.
3. Test brevity is important. Use approaches for re-use and brevity including using fixtures for repeated code, and using pytest parameterize for similar tests.
4. Use unittest.mock, unittest.patch and related test tools
5. After writing a new test, run it and ensure it works. Fix any issues you find.
