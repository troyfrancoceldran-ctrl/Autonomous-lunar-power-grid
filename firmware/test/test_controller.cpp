// test_controller.cpp — the C++ controller against the Python original.
//
// Replays firmware/test/controller_golden.json, which recorded what the real
// AutonomousController was SHOWN and what it DID at all 1440 ticks of a full
// synodic month. Every decision must match, including the 1429 where the
// answer was "do nothing" — a port that acts when the original stayed idle is
// just as wrong as one that misses an action, and far easier to miss.
//
//   cmake -S firmware -B firmware/build && cmake --build firmware/build
//   ./firmware/build/test_controller
//
// The JSON is parsed by a small reader below rather than a library: this is a
// fixed, machine-written file of numbers, and adding a dependency to read it
// would be the only dependency in the firmware tree.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "controller.hpp"

namespace {

std::string slurp(const char *path) {
    FILE *f = std::fopen(path, "rb");
    if (!f) { std::printf("  cannot open %s\n", path); std::exit(2); }
    std::string out;
    char buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) out.append(buf, n);
    std::fclose(f);
    return out;
}

/// Cursor over the golden file. Only what this fixed format needs.
struct Reader {
    const std::string &s;
    size_t i = 0;

    explicit Reader(const std::string &src) : s(src) {}

    bool seek(const char *key) {
        const size_t at = s.find(key, i);
        if (at == std::string::npos) return false;
        i = at + std::strlen(key);
        return true;
    }
    double number() {
        while (i < s.size() && (s[i] == ':' || s[i] == ',' || s[i] == ' ' ||
                                s[i] == '[')) ++i;
        char *end = nullptr;
        const double v = std::strtod(s.c_str() + i, &end);
        i = static_cast<size_t>(end - s.c_str());
        return v;
    }
    bool boolean() {
        while (i < s.size() && (s[i] == ':' || s[i] == ',' || s[i] == ' ')) ++i;
        const bool t = s.compare(i, 4, "true") == 0;
        i += t ? 4 : 5;
        return t;
    }
};

}  // namespace

int main() {
    const std::string src = slurp("firmware/test/controller_golden.json");
    Reader r(src);

    if (!r.seek("\"shed\"")) { std::printf("  malformed golden\n"); return 2; }
    const double shed_th = r.number();
    r.seek("\"restore\"");
    const double restore_th = r.number();
    r.seek("\"dwell\"");
    const double dwell = r.number();

    lunar::Controller controller(shed_th, restore_th, dwell);

    int ticks = 0, actions = 0, mismatches = 0;
    while (r.seek("{\"t\":")) {
        const double t = r.number();
        r.seek("\"soc\":");
        const double soc = r.number();
        r.seek("\"headroom\":");
        const double headroom = r.number();

        r.seek("\"loads\":");
        lunar::LoadView loads[lunar::MAX_LOADS];
        int count = 0;
        while (count < lunar::MAX_LOADS) {
            const size_t save = r.i;
            if (!r.seek("[")) break;
            // The loads array closes with "]]," — stop before the next key.
            if (src.compare(r.i - 2, 2, "]]") == 0) { r.i = save; break; }
            loads[count].priority = static_cast<int>(r.number());
            loads[count].shed = r.boolean();
            loads[count].demand_w = r.number();
            ++count;
            const size_t after = r.s.find_first_of("],", r.i);
            if (after != std::string::npos && r.s[after] == ']' &&
                after + 1 < r.s.size() && r.s[after + 1] == ']') {
                r.i = after + 2;
                break;
            }
        }

        r.seek("\"index\":");
        const int want_index = static_cast<int>(r.number());
        r.seek("\"shed\":");
        const bool want_shed = r.boolean();

        const lunar::Action got =
            controller.update(t, soc, headroom, loads, count);

        if (got.index != want_index ||
            (want_index >= 0 && got.shed != want_shed)) {
            if (mismatches < 8) {
                std::printf("  tick %4d t=%.1f soc=%.4f head=%.1f  "
                            "got (%d,%d)  want (%d,%d)\n",
                            ticks, t, soc, headroom, got.index,
                            static_cast<int>(got.shed), want_index,
                            static_cast<int>(want_shed));
            }
            ++mismatches;
        }
        if (want_index >= 0) ++actions;
        ++ticks;
    }

    std::printf("\n  %d ticks replayed, %d of them an action\n", ticks, actions);
    if (ticks == 0) { std::printf("  PARSED NOTHING — check the golden\n"); return 2; }
    if (mismatches == 0) {
        std::printf("  CONTROLLER CONFORMANCE PASS — the port decides exactly "
                    "as the Python original.\n");
        return 0;
    }
    std::printf("  CONTROLLER CONFORMANCE FAIL — %d divergences.\n", mismatches);
    return 1;
}
