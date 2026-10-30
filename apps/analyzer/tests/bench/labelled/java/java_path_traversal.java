import java.io.File;
import java.nio.file.Files;
import javax.servlet.http.HttpServletRequest;

public class DownloadHandler {
    public byte[] read(HttpServletRequest request) throws Exception {
        File file = new File("/srv/uploads/" + request.getParameter("f"));
        return Files.readAllBytes(file.toPath());
    }
}
