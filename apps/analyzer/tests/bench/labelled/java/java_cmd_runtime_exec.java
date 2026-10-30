import java.io.IOException;

public class PingService {
    public int ping(String host) throws IOException, InterruptedException {
        Process p = Runtime.getRuntime().exec("ping -c 1 " + host);
        return p.waitFor();
    }
}
