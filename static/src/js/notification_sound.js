/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { notificationService } from "@web/core/notifications/notification_service";

patch(notificationService, {
    start() {
        const result = super.start(...arguments);
        const originalAdd = result.add;

        result.add = (message, options) => {
            try {
                const audio = new Audio("/hr_resignation/static/src/sounds/notification.mp3");
                audio.play().catch(e => {
                    // Browsers might block audio if there was no user interaction yet
                    console.log("Notification sound play blocked or failed:", e);
                });
            } catch (err) {
                console.error("Error playing notification sound:", err);
            }
            return originalAdd(message, options);
        };

        return result;
    }
});
