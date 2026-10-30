import java.net.InetAddress;
import java.util.List;

public class PingService {
    public int ping(String host) throws Exception {
        if (!host.matches("[0-9.]{7,15}")) {
            throw new IllegalArgumentException("not an IPv4 address");
        }
        String address = InetAddress.getByName(host).getHostAddress();
        Process p = new ProcessBuilder(List.of("ping", "-c", "1", address)).start();
        return p.waitFor();
    }
}
