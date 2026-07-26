# Version History

**Pipeline Version: 9.9.9**

Fixture engine version deliberately outside any reasonable configured
supported range used in EngineBridgeTests, so tests can verify the
version-compatibility gate refuses command execution and artifact reads
*before* any other component (ProcessRunner, the artifact readers) is
ever invoked.
