#include <string>

class Session {
public:
    void set_user(const std::string &name) {
        if (name.size() > 32) return;
        user_ = name;
    }

private:
    std::string user_;
};
