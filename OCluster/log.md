# Changelog

## v6.0.0 (Current)
* Changed: Switched to parameterless `/relatedItems` calls based on diagnostic yield data to recover edges missed by typed calls.
* Changed: Normalized service URLs by stripping layer identifiers (e.g., `/FeatureServer/0` becomes `/FeatureServer`) to fix offline URL resolution mismatches.
* Removed: Dropped `GLOBAL_RELATED_TYPES` (`Item2Attachment`, `Item2Report`) after diagnostics proved they yield zero edges, saving roughly 1,800 API calls per run.
* Fixed: Handled `NoneType` JSON parsing errors for StoryMaps and Web Mapping Applications as expected errors, preventing infinite retry loops for items with legitimately empty payloads.
* Added: Spacejunk candidate detection logic combining connectivity, view counts, and modification age.

## v5.0.0 (Targeted Routing & Metadata)
* Added: Targeted `/relatedItems` calls using specific `relationshipTypes` for View Services, Forms, Solutions, and Map Areas.
* Added: Unscanned type logging to identify item types receiving zero API calls.
* Changed: Replaced `is_abandoned` with `is_unreferenced` for more accurate semantic signaling.
* Changed: Node metadata is now built fresh from the live inventory on every run. Only edges are cached to prevent stale views, tags, and access data.
* Fixed: Connection pool sized to `max(MAX_WORKERS, SIZE_WORKERS) + 2` to prevent pool exhaustion during size hydration.
* Fixed: Draft resource filtering now strictly requires `.json` extensions to prevent downloading binary files.
* Fixed: Resource listing failures now correctly mark the item as a failure for retry.

## v4.0.0 (Hydrated Size Enrichment)
* Added: Parallel file size enrichment using `gis.content.get()` to fetch actual file and attachment sizes in MB.
* Changed: Size enrichment runs incrementally, only targeting new, changed, or missing-size items.
* Fixed: Treated `-1` size values from search results as `None` (Unknown) rather than zero.
* Removed: Eliminated `/relatedItems` calls entirely for complex types (Web Maps, Dashboards) after proving `/data` parsing captures the same edges faster.

## v3.0.0 (Audit & Stability Fixes)
* Added: Schema versioning to force clean rescans when extraction rules change.
* Added: Offline URL map built during inventory to resolve service layer URLs to Item IDs without API calls.
* Added: Substring regex matching with hex lookarounds to catch IDs embedded in Arcade scripts and URLs.
* Added: Atomic file writes using temporary files and renames to prevent state corruption on crash.
* Fixed: Resolved `datetime` module collision by switching entirely to the `time` module.
* Fixed: Corrected inventory seen-set bug that dropped the oldest 100 items.
* Fixed: Adjusted date-range floor guard to fetch the first 10,000 items instead of skipping small ranges.
* Fixed: Implemented regex-based error classification with word boundaries to prevent false positives on hex strings.

## v2.0.0 (Performance & Payload Optimization)
* Added: Per-endpoint metrics tracking (call counts, execution time, failure rates).
* Added: Rolling ETA calculation based on a 100-item sliding window.
* Changed: Replaced `json.dumps` and full-string regex with recursive dictionary walking for payload parsing.
* Changed: Dropped redundant reverse `/relatedItems` calls (forward calls cover the same edges when processing the target item).
* Changed: Switched to indiscriminate retries only for 429 and 5xx errors. Client errors (4xx) fail immediately.
* Fixed: Suppressed `urllib3` InsecureRequestWarning at the module level.
* Fixed: Matched `ThreadPoolExecutor` worker count to the `urllib3` connection pool size to eliminate connection discard warnings.

## v1.0.0 (Initial Hybrid Architecture)
* Added: Replaced recursive `ItemGraph` traversal with a hybrid `/relatedItems` and `/data` JSON parsing engine.
* Added: Date-sliced bulk inventory fetching to bypass the 10,000 item search limit.
* Added: Local `networkx` graph construction for instant recursive blast radius calculations.
* Added: Incremental state tracking using item `modified` timestamps to skip unchanged items on subsequent runs.
* Added: Parallel execution via `ThreadPoolExecutor` for extraction and inventory tasks.
