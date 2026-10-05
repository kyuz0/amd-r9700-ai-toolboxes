# Serialized expert loading

The v0.4.4 ROCm 10 toolbox serializes target expert loading and hot-cache compaction across tensor-parallel workers to limit temporary host-memory allocations on 64 GB systems. Model initialization and generic postprocessing remain outside the lock; inference kernels and decoding arithmetic are unchanged. `R9V_SERIALIZE_EXPERT_LOAD=1` enables this startup adaptation, and the lock file belongs in the writable compilation cache.

The installer checks the exact loader hash from plugin `d378a252e44fb6320642e2ef367173d2a0e98059` and writes a patch identity manifest into the image. Review source changes before carrying the adaptation to another plugin revision.
