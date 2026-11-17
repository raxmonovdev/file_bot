/* Noutbuk uyqudan chiqqanda "wake" deb yozadi. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOMessage.h>
#include <IOKit/pwr_mgt/IOPMLib.h>
#include <stdio.h>

static io_connect_t root_port;

static void on_power(void *refcon, io_service_t service, natural_t message_type, void *argument) {
    (void)refcon;
    (void)service;
    switch (message_type) {
        case kIOMessageCanSystemSleep:
        case kIOMessageSystemWillSleep:
            IOAllowPowerChange(root_port, (intptr_t)argument);
            break;
        case kIOMessageSystemHasPoweredOn:
            printf("wake\n");
            fflush(stdout);
            break;
        default:
            break;
    }
}

int main(void) {
    IONotificationPortRef notify_port = NULL;
    io_object_t notifier = 0;

    root_port = IORegisterForSystemPower(NULL, &notify_port, on_power, &notifier);
    if (root_port == MACH_PORT_NULL) {
        fprintf(stderr, "uyqu kuzatuvchisi ishga tushmadi\n");
        return 1;
    }

    CFRunLoopAddSource(
        CFRunLoopGetCurrent(),
        IONotificationPortGetRunLoopSource(notify_port),
        kCFRunLoopDefaultMode
    );
    CFRunLoopRun();
    return 0;
}
