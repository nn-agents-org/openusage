import Foundation

struct MenuBarContent: Equatable {
    struct Item: Equatable, Identifiable {
        let id: String
        let provider: Provider
        let label: String
        let shortLabel: String
        let value: String
        var reset: String? = nil
    }

    let items: [Item]
    var overflow = 0
    var updateAvailable = false

    var isEmpty: Bool { items.isEmpty }

    var accessibilityText: String {
        let shown = items.map { "\($0.provider.fullName) \($0.label) \($0.value)" }
        let more = overflow > 0 ? ["\(overflow) more"] : []
        let update = updateAvailable ? ["Update available"] : []
        return (shown + more + update).joined(separator: "; ")
    }
}

@MainActor
enum MenuBarContentBuilder {
    private static let genericWords: Set<String> = ["models", "bot", "usage"]

    /// Only what's running out, or with `alwaysShows` every section of the Priority tab in its order, top to bottom,
    /// then every metric with a reading in dashboard order — the fork's Always Show lists healthy limits too.
    static func build(board: PriorityBoard, limit: MenuBarLimit, alwaysShows: Bool = false) -> MenuBarContent {
        guard limit != .iconOnly else { return MenuBarContent(items: []) }
        var counted = alwaysShows
            ? board.pinned.map { ($0.provider, $0.line) } + (board.attention + board.useItOrLoseIt).map { ($0.provider, $0.line) }
            : board.runningOut.map { ($0.provider, $0.line) }
        let usedUp = alwaysShows ? board.usedUp.map { ($0.provider, $0.line) } : []
        if alwaysShows {
            let listed = Set(counted.map { $0.1.id } + usedUp.map { $0.1.id })
            counted += board.everyMetric.filter { !listed.contains($0.1.id) }.map { ($0.provider, $0.line) }
        }
        let shown = (counted + usedUp).prefix(limit.count).map { provider, line in
            let label = line.data.title
            return MenuBarContent.Item(
                id: line.id,
                provider: provider,
                label: label,
                shortLabel: shortLabel(label),
                value: line.data.menuBarValue,
                reset: line.data.menuBarResetText()
            )
        }
        return MenuBarContent(items: shown, overflow: max(0, counted.count - shown.count))
    }

    static func shortLabel(_ label: String) -> String {
        var words = label.split(separator: " ")
        guard words.count > 1, let last = words.last, genericWords.contains(last.lowercased()) else { return label }
        words.removeLast()
        return words.joined(separator: " ")
    }
}
