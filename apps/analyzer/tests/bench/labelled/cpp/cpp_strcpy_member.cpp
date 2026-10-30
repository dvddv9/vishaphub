#include <cstring>

class Session {
public:
    void set_user(const char *name) {
        strcpy(user_, name);
    }

private:
    char user_[32];
};
