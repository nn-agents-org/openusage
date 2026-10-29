import Foundation

enum Formatters {
    static func monthDayLabel(_ date: Date) -> String {
        date.formatted(.dateTime.month(.abbreviated).day())
    }

    static func whenLabel(
        at date: Date,
        mode: ResetDisplayMode,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> String? {
        switch mode {
        case .relative:
            let seconds = date.timeIntervalSince(now)
            if seconds <= 5 * 60 { return imminent }
            return compactDuration(seconds)
        case .absolute:
            guard date.timeIntervalSince(now) > 0 else { return imminent }
            let dayDiff = calendar.dateComponents(
                [.day],
                from: calendar.startOfDay(for: now),
                to: calendar.startOfDay(for: date)
            ).day ?? 0
            let time = TimeFormatSetting.current.shortTime(date)
            if dayDiff <= 0 { return "today at \(time)" }
            if dayDiff == 1 { return "tomorrow at \(time)" }
            return "\(monthDayLabel(date)) at \(time)"
        }
    }

    static let imminent = "soon"

    static func compactClock(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        let days = calendar.dateComponents(
            [.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: date)
        ).day ?? 0
        if days <= 0 { return TimeFormatSetting.current.shortTime(date) }
        if days < 7 { return TimeFormatSetting.current.weekdayHour(date) }
        return monthDayLabel(date)
    }

    static func compactDuration(_ seconds: TimeInterval) -> String? {
        guard seconds.isFinite, seconds > 0 else { return nil }
        let totalMinutes = max(1, Int((seconds / 60).rounded(.up)))
        let days = totalMinutes / (24 * 60)
        let hours = (totalMinutes % (24 * 60)) / 60
        let minutes = totalMinutes % 60

        if days > 0 {
            return "\(days)d \(hours)h"
        }
        if hours > 0 {
            return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h"
        }
        return "\(minutes)m"
    }

    static func menuBarReset(_ seconds: TimeInterval) -> String? {
        guard seconds.isFinite, seconds > 0 else { return nil }
        let totalMinutes = max(1, Int((seconds / 60).rounded(.up)))
        let hours = totalMinutes / 60
        let days = hours / 24
        if days >= 1 {
            return "\(days)d"
        }
        if hours >= 1 {
            return "\(hours)h"
        }
        return "\(totalMinutes)m"
    }


    static func compactMenuBarReset(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }
    static func trayReset(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }
    static func menuBarCountdown(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }
    static func compactReset(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }
    static func resetCountdown(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }
    static func trayCountdown(_ seconds: TimeInterval) -> String? { menuBarReset(seconds) }

}
