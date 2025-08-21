## Python Test Guide

When writing tests for Python code:

1. Always use pytest for tests in Python code
2. Before writing tests, do a code review to check for potential issues in the code. Don't blindly write tests assuming the code works properly. If you believe there may be a bug but are uncertain, ask the user. If you're reasonably certain there is a bug, write a test showing it, confirm it fails, then ask the user if you were correct and if they want you to fix the issue.
3. Assume an appropriate test file already exists, find it, and appended tests to that file. Don't create new test files unless you've confirmed an appriopiate one does not exist.
4. Test brevity is important. Use approaches for re-use and brevity including using pytest fixtures for repeated code, and using pytest parametrize for similar tests.
5. Use unittest.mock, unittest.mock.patch and related test tools
6. After writing a new test, run it and ensure it works. Fix any issues you find.
