// harness.hpp — a test reporter in one header, with no dependencies.
//
// Deliberately not GoogleTest or Catch2. This has to build on a machine with
// no package manager configured and eventually cross-compile for a board, and
// a dependency that cannot be fetched is a test suite that stops being run.
//
// It mirrors the Python suite's behaviour in one specific way that matters:
// a test whose implementation does not exist yet reports SKIP, not FAIL. A
// half-finished feature should not produce a red build, because a red build
// gets ignored, and an ignored build stops catching anything.
#pragma once

#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

namespace harness {

/// Thrown by a stub. The runner turns it into a SKIP with the reason attached.
struct NotImplemented : std::logic_error {
    explicit NotImplemented(const std::string& what)
        : std::logic_error(what) {}
};

struct Case {
    const char* name;
    void (*fn)();
};

inline std::vector<Case>& registry() {
    static std::vector<Case> cases;
    return cases;
}

struct Register {
    Register(const char* name, void (*fn)()) { registry().push_back({name, fn}); }
};

/// Registers a test. Used as:  TEST(name) { ... }
#define TEST(NAME)                                                      \
    static void NAME();                                                 \
    static harness::Register reg_##NAME(#NAME, &NAME);                  \
    static void NAME()

struct Failure : std::runtime_error {
    explicit Failure(const std::string& what) : std::runtime_error(what) {}
};

inline void check(bool ok, const std::string& what) {
    if (!ok) throw Failure(what);
}

/// Relative comparison with an absolute floor, matching the Python suite's
/// convention: a value that should be zero and comes out 1e-18 is agreement,
/// not a 100 % error.
inline void close(double got, double want, double rel, const std::string& what) {
    const double diff = std::fabs(got - want);
    const double scale = std::fmax(std::fabs(got), std::fabs(want));
    if (diff <= 1e-12) return;
    if (diff > rel * scale) {
        char buf[256];
        std::snprintf(buf, sizeof buf, "%s — got %.10g, want %.10g (rel %.3g)",
                    what.c_str(), got, want, diff / (scale > 0 ? scale : 1));
        throw Failure(buf);
    }
}

inline int run() {
    int passed = 0, failed = 0, skipped = 0;
    std::vector<std::string> skips, fails;

    for (const auto& c : registry()) {
        try {
            c.fn();
            ++passed;
            std::printf(".");
        } catch (const NotImplemented& e) {
            ++skipped;
            std::printf("s");
            skips.push_back(std::string(c.name) + " — " + e.what());
        } catch (const std::exception& e) {
            ++failed;
            std::printf("F");
            fails.push_back(std::string(c.name) + " — " + e.what());
        }
    }
    std::printf("\n\n");

    for (const auto& f : fails)  std::printf("  FAIL  %s\n", f.c_str());
    for (const auto& s : skips)  std::printf("  SKIP  %s\n", s.c_str());
    if (!fails.empty() || !skips.empty()) std::printf("\n");

    std::printf("  %d passed, %d failed, %d skipped\n", passed, failed, skipped);
    return failed == 0 ? 0 : 1;
}

}  // namespace harness

int main() { return harness::run(); }
