#include <cstdlib>
#include <string>

int archive(const std::string &dir) {
    std::string cmd = "tar czf backup.tgz " + dir;
    return std::system(cmd.c_str());
}
